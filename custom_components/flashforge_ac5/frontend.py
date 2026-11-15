"""Serve and automatically load the optional dashboard card."""

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Make the card available in all dashboard modes without manual resources."""
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
