"""Shared entity plumbing for the FlashForge integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import FlashForgeDataUpdateCoordinator, FlashForgeRuntimeData
from .models import PrinterSnapshot


class FlashForgeEntity(CoordinatorEntity[FlashForgeDataUpdateCoordinator]):
    """Base class wiring an entity to the coordinator and the printer device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FlashForgeDataUpdateCoordinator,
        entry: ConfigEntry,
        unique_suffix: str,
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"

    @property
    def runtime_data(self) -> FlashForgeRuntimeData:
        """Return the config entry runtime data."""
        return self.entry.runtime_data

    @property
    def snapshot(self) -> PrinterSnapshot:
        """Return the latest printer snapshot."""
        return self.coordinator.data

    @property
    def device_info(self) -> DeviceInfo:
        """Describe the printer as a single device."""
        info = self.snapshot.info
        connections: set[tuple[str, str]] = set()
        if info.mac_address:
            connections.add((CONNECTION_NETWORK_MAC, info.mac_address.lower()))

        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            connections=connections or None,
            manufacturer=MANUFACTURER,
            model=info.model or ("Creator 5" if info.is_creator5 else "FlashForge Printer"),
            name=info.name or self.entry.title,
            serial_number=self.runtime_data.api.serial_number,
            sw_version=info.firmware_version or None,
            configuration_url=f"http://{self.runtime_data.api.host}",
        )
