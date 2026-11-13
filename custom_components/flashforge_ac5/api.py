"""Thin async wrapper around the ``flashforge-python-api`` client.

The library is synchronous-with-``await`` around aiohttp + a raw TCP channel.
This module isolates Home Assistant from its quirks:

* it maps the library's "returned False" style into typed exceptions so the
  config flow can tell "unreachable" from "wrong check code";
* it initialises the TCP control channel lazily, because the HTTP-only models
  (Creator 5 / Creator 5 Pro) have no TCP service at all;
* it serialises camera-URL probing and caches the result.
"""

from __future__ import annotations

import asyncio
import logging
import time

from flashforge import FlashForgeClient
from flashforge.exceptions import FlashForgeError
from flashforge.models import FFMachineInfo

_LOGGER = logging.getLogger(__name__)

# A failed camera probe must not be retried on every poll: the probe costs up to
# six seconds (HEAD then GET, three seconds each) and the printer's HTTP server
# is single threaded, so retrying it in the polling loop starves the video feed.
CAMERA_PROBE_RETRY_INTERVAL = 600.0  # seconds


class FlashForgeApiError(Exception):
    """Base error for this integration's API layer."""


class FlashForgeConnectionError(FlashForgeApiError):
    """The printer could not be reached over the network."""


class FlashForgeAuthError(FlashForgeApiError):
    """The printer was reached but rejected the serial number / check code."""


class FlashForgeApi:
    """Owns a single ``FlashForgeClient`` and its connection state."""

    def __init__(
        self,
        host: str,
        serial_number: str,
        check_code: str,
    ) -> None:
        self.host = host
        self.serial_number = serial_number
        self.check_code = check_code

        self._client = FlashForgeClient(host, serial_number, check_code)
        self._control_ready = False
        self._control_lock = asyncio.Lock()
        self._camera_url: str = ""
        self._camera_probe_lock = asyncio.Lock()
        self._camera_probe_not_before: float = 0.0

    @property
    def client(self) -> FlashForgeClient:
        """Return the underlying library client."""
        return self._client

    @property
    def http_only(self) -> bool:
        """Return True when the printer exposes no TCP control channel."""
        return self._client.http_only

    async def async_connect(self) -> FFMachineInfo:
        """Connect, verify credentials and return the first machine snapshot."""
        try:
            initialized = await self._client.initialize()
        except FlashForgeError as err:  # pragma: no cover - defensive
            raise FlashForgeConnectionError(str(err)) from err
        except (TimeoutError, OSError) as err:
            raise FlashForgeConnectionError(str(err)) from err

        if not initialized:
            raise FlashForgeConnectionError(f"Unable to reach the printer at {self.host}")

        # ``/detail`` is unauthenticated, so a wrong check code only shows up
        # here. Keep the two failures apart: the user can fix one of them.
        try:
            authorized = await self._client.send_product_command()
        except FlashForgeError as err:
            raise FlashForgeConnectionError(str(err)) from err

        if not authorized:
            raise FlashForgeAuthError("The printer rejected the serial number or check code")

        info = await self.async_get_machine_info()
        if info is None:
            raise FlashForgeConnectionError("The printer did not return machine information")
        return info

    async def async_get_machine_info(self) -> FFMachineInfo | None:
        """Fetch the full machine snapshot (``/detail``)."""
        try:
            return await self._client.info.get()
        except FlashForgeError as err:
            raise FlashForgeConnectionError(str(err)) from err
        except (TimeoutError, OSError) as err:
            raise FlashForgeConnectionError(str(err)) from err
        except Exception as err:
            raise FlashForgeConnectionError(str(err)) from err

    async def async_dispose(self) -> None:
        """Tear the connection down (HTTP session + TCP keep-alive)."""
        try:
            await self._client.dispose()
        except Exception as err:  # noqa: BLE001 - never block an unload
            _LOGGER.debug("Error while disposing the FlashForge client: %s", err)

    async def async_ensure_control(self) -> bool:
        """Initialise the TCP control channel once, if the model has one."""
        if self._client.http_only:
            return False
        if self._control_ready:
            return True

        async with self._control_lock:
            if self._control_ready:
                return True
            try:
                self._control_ready = await self._client.init_control()
            except Exception as err:  # noqa: BLE001 - control is optional
                _LOGGER.debug("Unable to initialise the TCP control channel: %s", err)
                self._control_ready = False
            return self._control_ready

    # ------------------------------------------------------------------
    # Camera
    # ------------------------------------------------------------------

    def cached_camera_url(self) -> str:
        """Return the camera URL discovered so far (may be empty)."""
        return self._camera_url

    async def async_ensure_camera_enabled(self) -> bool:
        """Ask the printer to power its camera on, if it supports that.

        Not every model exposes the camera control command; a refusal is
        expected there and must not be treated as an error.
        """
        if not self._client.is_pro:
            return False
        try:
            return await self._client.control.turn_camera_on()
        except Exception as err:  # noqa: BLE001 - optional capability
            _LOGGER.debug("Unable to enable the printer camera: %s", err)
            return False

    async def async_resolve_camera_url(
        self, info: FFMachineInfo | None, force: bool = False, probe: bool = False
    ) -> str:
        """Return a working MJPEG stream URL for the printer camera.

        The firmware usually reports its camera URL in ``/detail``, which is
        free to read. Only when it does not (older firmware, camera just
        switched on) is the OEM endpoint probed, and probing is an opt-in
        operation: it can block for six seconds, so the polling loop passes
        ``probe=False`` and only the entity setup or the refresh button ask for
        it.
        """
        if info is not None and info.camera_stream_url:
            self._camera_url = info.camera_stream_url
            # A URL reported by the firmware is authoritative again.
            self._camera_probe_not_before = 0.0
            return self._camera_url

        if self._camera_url and not force:
            return self._camera_url

        if not force and not probe:
            return self._camera_url

        if info is not None and not info.has_camera and not self._camera_url and not force:
            return ""

        if not force and time.monotonic() < self._camera_probe_not_before:
            # Probe failed recently; stay quiet instead of stalling the poll.
            return self._camera_url

        async with self._camera_probe_lock:
            # Another caller may have finished the probe while we waited.
            if self._camera_url and not force:
                return self._camera_url
            if not force and time.monotonic() < self._camera_probe_not_before:
                return self._camera_url

            try:
                detected = await self._client.detect_camera_stream()
            except Exception as err:  # noqa: BLE001 - probing must never raise
                _LOGGER.debug("Camera probe failed: %s", err)
                detected = ""

            if detected:
                self._camera_url = detected
                _LOGGER.debug("Detected camera stream at %s", detected)
            elif not force:
                self._camera_probe_not_before = (
                    time.monotonic() + CAMERA_PROBE_RETRY_INTERVAL
                )
                _LOGGER.debug(
                    "Camera probe found nothing; next attempt allowed in %.0f s",
                    CAMERA_PROBE_RETRY_INTERVAL,
                )

        return self._camera_url
