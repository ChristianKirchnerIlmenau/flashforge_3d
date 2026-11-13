"""Data update coordinator for the FlashForge integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FlashForgeApi, FlashForgeApiError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .models import PrinterSnapshot

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class FlashForgeRuntimeData:
    """Objects stored on ``ConfigEntry.runtime_data``."""

    api: FlashForgeApi
    coordinator: "FlashForgeDataUpdateCoordinator"


class FlashForgeDataUpdateCoordinator(DataUpdateCoordinator[PrinterSnapshot]):
    """Polls ``/detail`` and exposes one consistent snapshot to all entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: FlashForgeApi,
        update_interval: timedelta | None = None,
    ) -> None:
        """Initialise the coordinator."""
        self.entry = entry
        self.api = api
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.title}",
            update_interval=update_interval or timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _async_update_data(self) -> PrinterSnapshot:
        """Poll the printer once and translate failures into ``UpdateFailed``."""
        try:
            info = await self.api.async_get_machine_info()
        except FlashForgeApiError as err:
            raise UpdateFailed(str(err)) from err

        if info is None:
            raise UpdateFailed("The printer returned an empty /detail response")

        # Pick up the camera URL the firmware reports in /detail. The network
        # probe is deliberately not requested here: it can block for seconds and
        # the printer serves its HTTP API from a single thread, so probing on
        # every poll would stall both the sensors and the video feed.
        await self.api.async_resolve_camera_url(info)

        return PrinterSnapshot(info=info)
