"""Camera entity exposing the printer's built-in MJPEG stream.

FlashForge printers serve a plain MJPEG feed (``multipart/x-mixed-replace``) on
port 8080. The feed is passed through untouched instead of being handed to the
``stream`` component: advertising ``CameraEntityFeature.STREAM`` makes Home
Assistant transcode MJPEG to HLS through ffmpeg, which adds several seconds of
latency and a permanent encoding load for content browsers already render
natively.

The printer's HTTP server is single threaded, so the integration keeps exactly
one upstream camera connection. Every consumer -- the live view, the dashboard
thumbnail and notifications -- is served from that one reader.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress

import aiohttp
from aiohttp import web
from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import CAMERA_PORT
from .coordinator import FlashForgeDataUpdateCoordinator
from .entity import FlashForgeEntity

_LOGGER = logging.getLogger(__name__)

SNAPSHOT_PATH = "/?action=snapshot"

# The printer abandons requests slowly, so both the connect and the read phase
# need their own short limit instead of one generous total.
SNAPSHOT_TIMEOUT = aiohttp.ClientTimeout(total=4, sock_connect=3, sock_read=4)
STREAM_TIMEOUT = aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=20)

# How long a consumer waits for the next frame before giving up on this round.
FRAME_TIMEOUT = 6.0

# Multipart boundary for the re-broadcast stream. Home Assistant uses the same
# value for its own still-image stream, so keeping it eases debugging.
BOUNDARY = "--frameboundary"

# Consecutive empty waits after which a viewer is considered cut off.
MAX_FRAME_MISSES = 3

# Drop the shared reader if no frame arrives within this window, so a printer
# that went away is picked up again by the next request.
READER_IDLE_TIMEOUT = 30.0

# Stop trying the snapshot endpoint after this many consecutive failures: some
# firmwares answer 200 with a page that is not a JPEG. The verdict expires so a
# firmware update can bring the endpoint back without a reload.
SNAPSHOT_ATTEMPTS = 2
SNAPSHOT_RETRY_INTERVAL = 600.0

# Upper bound for the reassembly buffer of a single JPEG frame.
MAX_FRAME_BYTES = 2 * 1024 * 1024

SOI = b"\xff\xd8"
EOI = b"\xff\xd9"


def _extract_jpeg(buffer: bytearray) -> bytes | None:
    """Pop one complete JPEG off ``buffer`` and trim what was consumed.

    Boundary strings differ between firmware builds, so the JPEG start and end
    markers are used instead of parsing the multipart envelope. Consumed bytes
    are removed from the buffer, which keeps the search linear instead of
    rescanning an ever-growing array.
    """
    start = buffer.find(SOI)
    if start == -1:
        # Keep the final byte: an SOI marker may be split across two chunks.
        del buffer[:-1]
        return None

    end = buffer.find(EOI, start + 2)
    if end == -1:
        # Drop the multipart headers that precede a frame still in flight.
        if start:
            del buffer[:start]
        return None

    frame = bytes(buffer[start : end + 2])
    del buffer[: end + 2]
    return frame


class _MjpegFrameReader:
    """Hold one connection to the printer and publish its newest frame.

    Opening a connection per still image costs a full HTTP cycle, and because
    the printer serves MJPEG from a single thread those cycles also stall the
    live feed. One background reader removes both problems.
    """

    def __init__(self, session: aiohttp.ClientSession, url: str) -> None:
        self._session = session
        self._url = url
        self._task: asyncio.Task[None] | None = None
        self._frame: bytes | None = None
        self._version = 0
        self._finished = False
        self._last_request = 0.0
        self._condition = asyncio.Condition()

    @property
    def url(self) -> str:
        """Return the upstream URL this reader is bound to."""
        return self._url

    @property
    def closed(self) -> bool:
        """Return True when there is no live upstream connection."""
        return self._task is None or self._task.done()

    @property
    def latest_frame(self) -> bytes | None:
        """Return the newest frame received so far, without any waiting."""
        return self._frame

    async def async_frame(self, timeout: float) -> bytes | None:
        """Return the newest frame, waiting up to ``timeout`` for a new one."""
        self._last_request = asyncio.get_running_loop().time()
        self._ensure_running()
        target = self._version + 1

        try:
            async with asyncio.timeout(timeout):
                async with self._condition:
                    await self._condition.wait_for(
                        lambda: self._version >= target or self._finished
                    )
                    if self._version >= target:
                        return self._frame
                    return None
        except TimeoutError:
            _LOGGER.debug("Timed out waiting for a camera frame from %s", self._url)
            return None

    async def async_close(self) -> None:
        """Stop the background reader."""
        task, self._task = self._task, None
        if task is None or task.done():
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    def _ensure_running(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._finished = False
        self._last_request = asyncio.get_running_loop().time()
        self._task = asyncio.create_task(self._async_read())

    async def _async_read(self) -> None:
        """Read the multipart stream and publish every complete frame."""
        buffer = bytearray()
        try:
            async with self._session.get(
                self._url, timeout=STREAM_TIMEOUT, allow_redirects=False
            ) as response:
                if response.status != 200:
                    _LOGGER.debug("Camera stream returned HTTP %s", response.status)
                    return

                last_frame_at = asyncio.get_running_loop().time()
                async for chunk in response.content.iter_any():
                    buffer.extend(chunk)

                    frame = _extract_jpeg(buffer)
                    while frame is not None:
                        await self._publish(frame)
                        last_frame_at = asyncio.get_running_loop().time()
                        frame = _extract_jpeg(buffer)

                    if len(buffer) > MAX_FRAME_BYTES:
                        _LOGGER.debug("Discarding an oversized camera frame buffer")
                        buffer.clear()

                    # Close the connection once nothing has asked for a frame
                    # for a while: the printer only accepts one at a time.
                    now = asyncio.get_running_loop().time()
                    if now - max(last_frame_at, self._last_request) > READER_IDLE_TIMEOUT:
                        _LOGGER.debug("Camera stream went idle; dropping the connection")
                        return
        except asyncio.CancelledError:
            raise
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            _LOGGER.debug("Camera stream read failed: %s", err)
        finally:
            self._finished = True
            with suppress(RuntimeError):
                async with self._condition:
                    self._condition.notify_all()

    async def _publish(self, frame: bytes) -> None:
        async with self._condition:
            self._frame = frame
            self._version += 1
            self._condition.notify_all()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the camera platform."""
    coordinator: FlashForgeDataUpdateCoordinator = entry.runtime_data.coordinator
    if not coordinator.data.info.has_camera:
        _LOGGER.debug(
            "Printer %s reports no camera; skipping the camera entity",
            coordinator.api.host,
        )
        return

    # One probe at setup time is worth its cost: it covers firmware that does
    # not advertise its camera URL in /detail. Anything later comes from the
    # snapshot endpoint or from the refresh button, never from the polling loop.
    await coordinator.api.async_resolve_camera_url(coordinator.data.info, probe=True)

    async_add_entities([FlashForgeCamera(coordinator, entry)])


class FlashForgeCamera(FlashForgeEntity, Camera):
    """Live view and stills from the printer camera.

    ``CameraEntityFeature.STREAM`` is deliberately not advertised. With it Home
    Assistant forces the MJPEG feed through ffmpeg into HLS (roughly 5-12 s of
    latency plus a constant encoding load). Without it the frontend consumes
    ``/api/camera_proxy_stream`` directly, which is served from the shared
    reader below.
    """

    _attr_translation_key = "camera"
    _attr_brand = "FlashForge"

    def __init__(
        self,
        coordinator: FlashForgeDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialise the camera entity.

        ``Camera.__init__`` must be called explicitly: the MRO puts
        ``BaseCoordinatorEntity`` between us and ``Camera``, and that class does
        not chain to ``super().__init__()``. Without this call ``stream``,
        ``content_type`` and ``access_tokens`` are never created, which breaks
        the camera stream and ``entity_picture`` at runtime.
        """
        super().__init__(coordinator, entry, "camera")
        Camera.__init__(self)
        self._frame_reader: _MjpegFrameReader | None = None
        self._reader_lock = asyncio.Lock()
        self._snapshot_failures = 0
        self._snapshot_retry_at = 0.0

    async def async_added_to_hass(self) -> None:
        """Turn the printer camera on once the entity is registered."""
        await super().async_added_to_hass()
        await self.runtime_data.api.async_ensure_camera_enabled()

    async def async_will_remove_from_hass(self) -> None:
        """Stop the shared reader so no socket outlives the entity."""
        reader, self._frame_reader = self._frame_reader, None
        if reader is not None:
            await reader.async_close()
        await super().async_will_remove_from_hass()

    @property
    def _stream_url(self) -> str:
        """Return the best known MJPEG URL for this printer."""
        api = self.runtime_data.api
        return api.cached_camera_url() or api.camera_stream_url

    @property
    def _snapshot_url(self) -> str:
        """Return the one-shot snapshot URL for this printer."""
        return f"http://{self.runtime_data.api.host}:{CAMERA_PORT}{SNAPSHOT_PATH}"

    async def _async_reader(self) -> _MjpegFrameReader:
        """Return the shared reader, rebinding it if the URL changed."""
        url = self._stream_url
        async with self._reader_lock:
            reader = self._frame_reader
            if reader is not None and reader.url == url:
                return reader

            if reader is not None:
                # The refresh button found a different endpoint: start over.
                await reader.async_close()

            reader = _MjpegFrameReader(async_get_clientsession(self.hass), url)
            self._frame_reader = reader
            return reader

    async def handle_async_mjpeg_stream(
        self, request: web.Request
    ) -> web.StreamResponse | None:
        """Serve the printer feed as MJPEG, fed by the shared reader.

        Re-broadcasting the decoded frames (instead of piping the upstream
        socket) is what allows several viewers at once against a printer that
        accepts a single camera connection. The envelope matches what the
        camera component itself emits, so browsers and ffmpeg accept it.
        """
        reader = await self._async_reader()

        response = web.StreamResponse()
        response.content_type = f"multipart/x-mixed-replace; boundary={BOUNDARY}"
        await response.prepare(request)

        async def write_frame(frame: bytes) -> None:
            await response.write(
                (
                    f"--{BOUNDARY}\r\n"
                    f"Content-Type: image/jpeg\r\n"
                    f"Content-Length: {len(frame)}\r\n\r\n"
                ).encode()
                + frame
                + b"\r\n"
            )

        first_frame = True
        misses = 0

        try:
            while True:
                frame = await reader.async_frame(FRAME_TIMEOUT)
                if frame is None:
                    # One missed frame is normal while the printer reconnects;
                    # give up only once the feed has clearly stopped.
                    misses += 1
                    if misses >= MAX_FRAME_MISSES:
                        _LOGGER.debug("Camera feed stopped; closing the viewer")
                        break
                    continue

                misses = 0
                await write_frame(frame)

                # Chrome always renders the previous frame, so the first one is
                # sent twice to make the live view appear immediately.
                if first_frame:
                    await write_frame(frame)
                    first_frame = False
        except (ConnectionResetError, aiohttp.ClientError) as err:
            _LOGGER.debug("Camera viewer disconnected: %s", err)

        return response

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return one JPEG frame for dashboards and notifications.

        A live reader already holds a recent frame, so it is reused instead of
        asking the printer for a snapshot: the camera server is single threaded
        and a snapshot request would queue behind the open stream.
        """
        reader = self._frame_reader
        if reader is not None and not reader.closed:
            if (frame := reader.latest_frame) is not None:
                return frame
            return await reader.async_frame(FRAME_TIMEOUT)

        if self._snapshot_failures < SNAPSHOT_ATTEMPTS:
            frame = await self._async_snapshot()
            if frame is not None:
                self._snapshot_failures = 0
                self._snapshot_retry_at = 0.0
                return frame

            self._snapshot_failures += 1
            if self._snapshot_failures >= SNAPSHOT_ATTEMPTS:
                self._snapshot_retry_at = time.monotonic() + SNAPSHOT_RETRY_INTERVAL
                _LOGGER.debug(
                    "Printer at %s has no working snapshot endpoint; "
                    "using the shared stream reader instead",
                    self.runtime_data.api.host,
                )
        elif time.monotonic() >= self._snapshot_retry_at:
            # Enough time passed; give the endpoint another chance.
            self._snapshot_failures = 0

        reader = await self._async_reader()
        if (frame := reader.latest_frame) is not None:
            return frame
        return await reader.async_frame(FRAME_TIMEOUT)

    async def _async_snapshot(self) -> bytes | None:
        """Fetch a single JPEG from the snapshot endpoint, if there is one."""
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                self._snapshot_url, timeout=SNAPSHOT_TIMEOUT, allow_redirects=False
            ) as response:
                if response.status != 200:
                    return None
                data = await response.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Camera snapshot request failed: %s", err)
            return None

        # Some firmwares answer 200 with an error page, so verify the magic.
        if data[:2] != SOI:
            return None
        return data
