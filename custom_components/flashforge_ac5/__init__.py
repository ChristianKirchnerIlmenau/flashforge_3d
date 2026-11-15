"""Set up the FlashForge 3D Printer integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api import (
    FlashForgeApi,
    FlashForgeApiError,
    FlashForgeAuthError,
    FlashForgeConnectionError,
)
from .const import (
    CONF_CHECK_CODE,
    CONF_FORCE_LED_CONTROL,
    CONF_SERIAL_NUMBER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import FlashForgeDataUpdateCoordinator, FlashForgeRuntimeData

_LOGGER = logging.getLogger(__name__)

type FlashForgeConfigEntry = ConfigEntry[FlashForgeRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: FlashForgeConfigEntry) -> bool:
    """Connect to the printer and forward the platforms."""
    api = FlashForgeApi(
        host=entry.data[CONF_HOST],
        serial_number=entry.data[CONF_SERIAL_NUMBER],
        check_code=entry.data[CONF_CHECK_CODE],
        force_led_control=entry.options.get(CONF_FORCE_LED_CONTROL, False),
    )

    try:
        await api.async_connect()
    except FlashForgeAuthError as err:
        await api.async_dispose()
        # Auth failures must not retry blindly: HA shows a re-auth prompt instead.
        raise ConfigEntryAuthFailed(
            "The printer rejected the stored serial number or check code"
        ) from err
    except FlashForgeConnectionError as err:
        await api.async_dispose()
        raise ConfigEntryNotReady(
            f"Unable to connect to the printer at {api.host}: {err}"
        ) from err
    except FlashForgeApiError as err:  # pragma: no cover - defensive
        await api.async_dispose()
        raise ConfigEntryNotReady(str(err)) from err

    scan_interval = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
    coordinator = FlashForgeDataUpdateCoordinator(
        hass,
        entry,
        api,
        update_interval=timedelta(seconds=scan_interval),
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = FlashForgeRuntimeData(api=api, coordinator=coordinator)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FlashForgeConfigEntry) -> bool:
    """Unload the platforms and close the printer connection."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.api.async_dispose()
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: FlashForgeConfigEntry) -> None:
    """Apply option changes by reloading the entry."""
    _LOGGER.debug("%s options updated; reloading", DOMAIN)
    await hass.config_entries.async_reload(entry.entry_id)
