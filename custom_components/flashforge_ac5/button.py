"""Buttons for print job control and printer maintenance actions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
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
class FlashForgeButtonDescription(ButtonEntityDescription):
    """Button description with an action and an availability rule."""

    # ``False`` means "the printer refused"; any other value is treated as
    # success, so actions that return data (a resolved URL) fit the same hook.
    press_fn: Callable[[FlashForgeApi, FlashForgeDataUpdateCoordinator], Awaitable[object]]
    available_fn: Callable[[PrinterSnapshot], bool] = lambda snapshot: True


async def _pause(api: FlashForgeApi, coordinator: FlashForgeDataUpdateCoordinator) -> bool:
    await api.async_ensure_control()
    return await api.client.pause_print()


async def _resume(api: FlashForgeApi, coordinator: FlashForgeDataUpdateCoordinator) -> bool:
    await api.async_ensure_control()
    return await api.client.resume_print()


async def _cancel(api: FlashForgeApi, coordinator: FlashForgeDataUpdateCoordinator) -> bool:
    await api.async_ensure_control()
    return await api.client.emergency_stop()


async def _clear_platform(
    api: FlashForgeApi, coordinator: FlashForgeDataUpdateCoordinator
) -> bool:
    await api.async_ensure_control()
    return await api.client.job_control.clear_platform()


async def _home_axes(api: FlashForgeApi, coordinator: FlashForgeDataUpdateCoordinator) -> bool:
    await api.async_ensure_control()
    return await api.client.home_all_axes()


async def _refresh_camera(
    api: FlashForgeApi, coordinator: FlashForgeDataUpdateCoordinator
) -> str | None:
    info = coordinator.data.info
    await api.async_ensure_camera_enabled()
    return await api.async_resolve_camera_url(info, force=True)


BUTTONS: tuple[FlashForgeButtonDescription, ...] = (
    FlashForgeButtonDescription(
        key="pause_print",
        translation_key="pause_print",
        icon="mdi:pause",
        press_fn=_pause,
        available_fn=lambda s: s.info.machine_state.value == "printing",
    ),
    FlashForgeButtonDescription(
        key="resume_print",
        translation_key="resume_print",
        icon="mdi:play",
        press_fn=_resume,
        available_fn=lambda s: s.is_paused,
    ),
    FlashForgeButtonDescription(
        key="cancel_print",
        translation_key="cancel_print",
        icon="mdi:stop",
        press_fn=_cancel,
        available_fn=lambda s: s.is_active_print,
    ),
    FlashForgeButtonDescription(
        key="clear_platform",
        translation_key="clear_platform",
        icon="mdi:delete-sweep",
        press_fn=_clear_platform,
        available_fn=lambda s: s.info.machine_state.value in ("completed", "cancelled", "ready"),
    ),
    FlashForgeButtonDescription(
        key="home_axes",
        translation_key="home_axes",
        icon="mdi:axis-arrow",
        press_fn=_home_axes,
        available_fn=lambda s: not s.is_active_print,
    ),
    FlashForgeButtonDescription(
        key="refresh_camera",
        translation_key="refresh_camera",
        icon="mdi:camera-retake",
        press_fn=_refresh_camera,
        available_fn=lambda s: s.info.has_camera,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform."""
    coordinator: FlashForgeDataUpdateCoordinator = entry.runtime_data.coordinator
    async_add_entities(
        FlashForgeButton(coordinator, entry, description) for description in BUTTONS
    )


class FlashForgeButton(FlashForgeEntity, ButtonEntity):
    """A one-shot printer command."""

    entity_description: FlashForgeButtonDescription

    def __init__(
        self,
        coordinator: FlashForgeDataUpdateCoordinator,
        entry: ConfigEntry,
        description: FlashForgeButtonDescription,
    ) -> None:
        """Initialise the button."""
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description
        self._attr_translation_key = description.translation_key

    @property
    def available(self) -> bool:
        """Return whether the command makes sense right now."""
        if not super().available:
            return False
        try:
            return self.entity_description.available_fn(self.snapshot)
        except Exception:  # noqa: BLE001 - defensive against firmware drift
            return False

    async def async_press(self) -> None:
        """Execute the command and refresh the snapshot afterwards."""
        try:
            result = await self.entity_description.press_fn(self.runtime_data.api, self.coordinator)
        except Exception as err:
            raise HomeAssistantError(
                f"FlashForge command '{self.entity_description.key}' failed: {err}"
            ) from err

        if result is False:
            raise HomeAssistantError(
                f"The printer rejected the '{self.entity_description.key}' command"
            )

        await self.coordinator.async_request_refresh()
