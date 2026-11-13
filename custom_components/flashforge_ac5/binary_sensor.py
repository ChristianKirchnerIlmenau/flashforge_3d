"""Binary sensors for printing state, door, fans and connectivity."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import FlashForgeDataUpdateCoordinator
from .entity import FlashForgeEntity
from .models import PrinterSnapshot


@dataclass(frozen=True, kw_only=True)
class FlashForgeBinarySensorDescription(BinarySensorEntityDescription):
    """Binary sensor description with value accessor and availability rule."""

    value_fn: Callable[[PrinterSnapshot], bool]
    available_fn: Callable[[PrinterSnapshot], bool] = lambda snapshot: True


BINARY_SENSORS: tuple[FlashForgeBinarySensorDescription, ...] = (
    FlashForgeBinarySensorDescription(
        key="printing",
        translation_key="printing",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda s: s.info.machine_state.value in ("printing", "pausing"),
        icon="mdi:printer-3d",
    ),
    FlashForgeBinarySensorDescription(
        key="paused",
        translation_key="paused",
        value_fn=lambda s: s.is_paused,
        icon="mdi:pause-circle-outline",
    ),
    FlashForgeBinarySensorDescription(
        key="door",
        translation_key="door",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda s: s.info.door_open,
        available_fn=lambda s: s.info.has_door_sensor,
        icon="mdi:door",
    ),
    FlashForgeBinarySensorDescription(
        key="problem",
        translation_key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda s: s.info.machine_state.value == "error",
        icon="mdi:alert-circle",
    ),
    FlashForgeBinarySensorDescription(
        key="camera_available",
        translation_key="camera_available",
        value_fn=lambda s: s.info.has_camera,
        icon="mdi:video",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    coordinator: FlashForgeDataUpdateCoordinator = entry.runtime_data.coordinator
    async_add_entities(
        FlashForgeBinarySensor(coordinator, entry, description)
        for description in BINARY_SENSORS
    )


class FlashForgeBinarySensor(FlashForgeEntity, BinarySensorEntity):
    """A boolean flag derived from the printer snapshot."""

    entity_description: FlashForgeBinarySensorDescription

    def __init__(
        self,
        coordinator: FlashForgeDataUpdateCoordinator,
        entry: ConfigEntry,
        description: FlashForgeBinarySensorDescription,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description
        self._attr_translation_key = description.translation_key

    @property
    def available(self) -> bool:
        """Return whether the printer still reports this flag."""
        if not super().available:
            return False
        try:
            return self.entity_description.available_fn(self.snapshot)
        except Exception:  # noqa: BLE001 - defensive against firmware drift
            return False

    @property
    def is_on(self) -> bool:
        """Return the current boolean value."""
        try:
            return self.entity_description.value_fn(self.snapshot)
        except Exception:  # noqa: BLE001
            return False
