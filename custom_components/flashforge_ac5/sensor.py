"""Sensors exposing print progress, temperatures and printer statistics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import FlashForgeDataUpdateCoordinator
from .entity import FlashForgeEntity
from .models import PrinterSnapshot


@dataclass(frozen=True, kw_only=True)
class FlashForgeSensorDescription(SensorEntityDescription):
    """Sensor description with a value accessor and availability rule."""

    value_fn: Callable[[PrinterSnapshot], StateType | datetime]
    available_fn: Callable[[PrinterSnapshot], bool] = lambda snapshot: True


def _eta(snapshot: PrinterSnapshot) -> datetime | None:
    """Return the projected completion time when the print is advancing.

    The library builds ``completion_time`` as a naive local timestamp, and HA
    requires a timezone-aware value for a TIMESTAMP sensor, so attach it here.
    ``astimezone()`` on a naive datetime assumes the process-local zone, which
    is exactly the zone the library used to compute it.
    """
    completion = snapshot.info.completion_time
    if completion is None:
        return None
    return completion.astimezone()


SENSORS: tuple[FlashForgeSensorDescription, ...] = (
    FlashForgeSensorDescription(
        key="machine_state",
        translation_key="machine_state",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "ready",
            "busy",
            "calibrating",
            "error",
            "heating",
            "printing",
            "pausing",
            "paused",
            "cancelled",
            "completed",
            "unknown",
        ],
        value_fn=lambda s: s.info.machine_state.value,
        icon="mdi:printer-3d",
    ),
    FlashForgeSensorDescription(
        key="print_progress",
        translation_key="print_progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.info.print_progress_int,
        icon="mdi:progress-clock",
    ),
    FlashForgeSensorDescription(
        key="current_layer",
        translation_key="current_layer",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.info.current_print_layer,
        available_fn=lambda s: s.info.total_print_layers > 0,
        icon="mdi:layers-triple",
    ),
    FlashForgeSensorDescription(
        key="total_layers",
        translation_key="total_layers",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.info.total_print_layers,
        available_fn=lambda s: s.info.total_print_layers > 0,
        icon="mdi:layers-triple-outline",
    ),
    FlashForgeSensorDescription(
        key="remaining_time",
        translation_key="remaining_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda s: round(s.info.estimated_time / 60),
        available_fn=lambda s: s.is_active_print and s.info.estimated_time > 0,
        icon="mdi:timer-sand",
    ),
    FlashForgeSensorDescription(
        key="print_eta",
        translation_key="print_eta",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_eta,
        available_fn=lambda s: s.is_active_print,
        icon="mdi:clock-end",
    ),
    FlashForgeSensorDescription(
        key="print_file",
        translation_key="print_file",
        value_fn=lambda s: s.info.print_file_name or None,
        available_fn=lambda s: bool(s.info.print_file_name),
        icon="mdi:file-document-outline",
    ),
    FlashForgeSensorDescription(
        key="nozzle_temperature",
        translation_key="nozzle_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: round(s.info.extruder.current, 1),
        icon="mdi:thermometer-high",
    ),
    FlashForgeSensorDescription(
        key="nozzle_target_temperature",
        translation_key="nozzle_target_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: round(s.info.extruder.set, 1),
        icon="mdi:thermometer-chevron-up",
    ),
    FlashForgeSensorDescription(
        key="bed_temperature",
        translation_key="bed_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: round(s.info.print_bed.current, 1),
        icon="mdi:thermometer-low",
    ),
    FlashForgeSensorDescription(
        key="bed_target_temperature",
        translation_key="bed_target_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: round(s.info.print_bed.set, 1),
        icon="mdi:thermometer-chevron-up",
    ),
    FlashForgeSensorDescription(
        key="chamber_temperature",
        translation_key="chamber_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: round(s.info.chamber.current, 1) if s.info.chamber else None,
        available_fn=lambda s: s.info.has_chamber_sensor and s.info.chamber is not None,
        icon="mdi:thermometer",
    ),
    FlashForgeSensorDescription(
        key="estimated_filament_length",
        translation_key="estimated_filament_length",
        native_unit_of_measurement=UnitOfLength.METERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: round(s.info.est_length, 2),
        available_fn=lambda s: s.info.est_length > 0,
        icon="mdi:tape-measure",
    ),
    FlashForgeSensorDescription(
        key="estimated_filament_weight",
        translation_key="estimated_filament_weight",
        native_unit_of_measurement="g",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: round(s.info.est_weight, 1),
        available_fn=lambda s: s.info.est_weight > 0,
        icon="mdi:weight-gram",
    ),
    FlashForgeSensorDescription(
        key="filament_type",
        translation_key="filament_type",
        value_fn=lambda s: s.info.filament_type or None,
        available_fn=lambda s: bool(s.info.filament_type),
        icon="mdi:printer-3d-nozzle",
    ),
    FlashForgeSensorDescription(
        key="print_speed",
        translation_key="print_speed",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.info.print_speed_adjust or s.info.current_print_speed,
        icon="mdi:speedometer",
    ),
    FlashForgeSensorDescription(
        key="print_duration",
        translation_key="print_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: round(s.info.print_duration / 60),
        available_fn=lambda s: s.info.print_duration > 0,
        icon="mdi:timer-outline",
    ),
    FlashForgeSensorDescription(
        key="total_print_time",
        translation_key="total_print_time",
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda s: round(s.info.cumulative_print_time / 60, 1),
        icon="mdi:history",
    ),
    FlashForgeSensorDescription(
        key="total_filament_used",
        translation_key="total_filament_used",
        native_unit_of_measurement=UnitOfLength.METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda s: round(s.info.cumulative_filament, 2),
        icon="mdi:filament",
    ),
    FlashForgeSensorDescription(
        key="tvoc",
        translation_key="tvoc",
        native_unit_of_measurement="µg/m³",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: round(s.info.tvoc, 1),
        available_fn=lambda s: s.info.tvoc > 0,
        icon="mdi:air-filter",
    ),
    FlashForgeSensorDescription(
        key="error_code",
        translation_key="error_code",
        value_fn=lambda s: s.info.error_code or None,
        available_fn=lambda s: bool(s.info.error_code),
        icon="mdi:alert-circle-outline",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator: FlashForgeDataUpdateCoordinator = entry.runtime_data.coordinator
    async_add_entities(
        FlashForgeSensor(coordinator, entry, description) for description in SENSORS
    )


class FlashForgeSensor(FlashForgeEntity, SensorEntity):
    """A single value read from the printer snapshot."""

    entity_description: FlashForgeSensorDescription

    def __init__(
        self,
        coordinator: FlashForgeDataUpdateCoordinator,
        entry: ConfigEntry,
        description: FlashForgeSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description
        self._attr_translation_key = description.translation_key

    @property
    def available(self) -> bool:
        """Return whether the printer still reports this value."""
        if not super().available:
            return False
        try:
            return self.entity_description.available_fn(self.snapshot)
        except Exception:  # noqa: BLE001 - never break the whole entity
            return False

    @property
    def native_value(self) -> StateType | datetime | None:
        """Return the current value."""
        try:
            return self.entity_description.value_fn(self.snapshot)
        except Exception:  # noqa: BLE001 - defensive against firmware drift
            return None
