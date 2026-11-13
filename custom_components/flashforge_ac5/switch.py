"""Switches for the printer light, filament runout sensor and filtration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import FlashForgeApi
from .coordinator import FlashForgeDataUpdateCoordinator
from .entity import FlashForgeEntity
from .models import PrinterSnapshot

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class FlashForgeSwitchDescription(SwitchEntityDescription):
    """Switch description with turn-on/turn-off actions."""

    turn_on_fn: Callable[[FlashForgeApi], Awaitable[bool]]
    turn_off_fn: Callable[[FlashForgeApi], Awaitable[bool]]
    is_on_fn: Callable[[PrinterSnapshot], bool]
    available_fn: Callable[[PrinterSnapshot], bool] = lambda snapshot: True


async def _led_on(api: FlashForgeApi) -> bool:
    return await api.client.control.set_led_on()


async def _led_off(api: FlashForgeApi) -> bool:
    return await api.client.control.set_led_off()


async def _filtration_on(api: FlashForgeApi) -> bool:
    return await api.client.control.set_internal_filtration_on()


async def _filtration_off(api: FlashForgeApi) -> bool:
    return await api.client.control.set_filtration_off()


SWITCHES: tuple[FlashForgeSwitchDescription, ...] = (
    FlashForgeSwitchDescription(
        key="led",
        translation_key="led",
        device_class=SwitchDeviceClass.SWITCH,
        icon="mdi:lightbulb",
        turn_on_fn=_led_on,
        turn_off_fn=_led_off,
        is_on_fn=lambda s: s.info.lights_on,
    ),
    FlashForgeSwitchDescription(
        key="internal_filtration",
        translation_key="internal_filtration",
        device_class=SwitchDeviceClass.SWITCH,
        icon="mdi:air-purifier",
        turn_on_fn=_filtration_on,
        turn_off_fn=_filtration_off,
        is_on_fn=lambda s: s.info.internal_fan_on,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    coordinator: FlashForgeDataUpdateCoordinator = entry.runtime_data.coordinator
    api = entry.runtime_data.api

    # Both switches map onto capabilities advertised by /product: a printer
    # without the hardware only ever answers False, so creating the entity
    # would produce a control that can never work. Skip those instead.
    capabilities = {
        "led": (api.client.led_control, "no LED control"),
        "internal_filtration": (api.client.filtration_control, "no filtration control"),
    }

    entities: list[FlashForgeSwitch] = []
    for description in SWITCHES:
        supported, reason = capabilities.get(description.key, (True, ""))
        if not supported:
            _LOGGER.debug(
                "%s reports %s; skipping the %s switch",
                api.host,
                reason,
                description.key,
            )
            continue
        entities.append(FlashForgeSwitch(coordinator, entry, description))

    async_add_entities(entities)


class FlashForgeSwitch(FlashForgeEntity, SwitchEntity):
    """A boolean printer setting."""

    entity_description: FlashForgeSwitchDescription

    def __init__(
        self,
        coordinator: FlashForgeDataUpdateCoordinator,
        entry: ConfigEntry,
        description: FlashForgeSwitchDescription,
    ) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description
        self._attr_translation_key = description.translation_key

    @property
    def available(self) -> bool:
        """Return whether the printer reports this setting."""
        if not super().available:
            return False
        try:
            return self.entity_description.available_fn(self.snapshot)
        except Exception:  # noqa: BLE001 - defensive against firmware drift
            return False

    @property
    def is_on(self) -> bool:
        """Return the reported state."""
        try:
            return self.entity_description.is_on_fn(self.snapshot)
        except Exception:  # noqa: BLE001
            return False

    async def async_turn_on(self, **kwargs) -> None:
        """Switch the setting on."""
        await self._async_apply(self.entity_description.turn_on_fn)

    async def async_turn_off(self, **kwargs) -> None:
        """Switch the setting off."""
        await self._async_apply(self.entity_description.turn_off_fn)

    async def _async_apply(self, action: Callable[[FlashForgeApi], Awaitable[bool]]) -> None:
        try:
            result = await action(self.runtime_data.api)
        except Exception as err:
            raise HomeAssistantError(
                f"FlashForge command '{self.entity_description.key}' failed: {err}"
            ) from err

        if not result:
            raise HomeAssistantError(
                f"The printer rejected the '{self.entity_description.key}' command"
            )

        await self.coordinator.async_request_refresh()
