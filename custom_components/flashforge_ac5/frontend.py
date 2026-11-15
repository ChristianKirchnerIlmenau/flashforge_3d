"""Serve and automatically load the optional dashboard card."""

import asyncio
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN

_FRONTEND_SETUP_LOCK: HassKey[asyncio.Lock] = HassKey(
    f"{DOMAIN}_frontend_setup_lock"
)
_FRONTEND_SETUP_COMPLETE: HassKey[bool] = HassKey(
    f"{DOMAIN}_frontend_setup_complete"
)


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Make the card available in all dashboard modes without manual resources."""
    lock = hass.data.setdefault(_FRONTEND_SETUP_LOCK, asyncio.Lock())
    async with lock:
        if hass.data.get(_FRONTEND_SETUP_COMPLETE):
            return

        integration = await async_get_integration(hass, DOMAIN)
        url = f"/{DOMAIN}/flashforge-card.js"
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    url,
                    str(Path(__file__).parent / "www" / "flashforge-card.js"),
                    False,
                )
            ]
        )
        add_extra_js_url(hass, f"{url}?v={integration.version}")
        hass.data[_FRONTEND_SETUP_COMPLETE] = True
