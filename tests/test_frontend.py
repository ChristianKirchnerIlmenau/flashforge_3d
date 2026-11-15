"""Tests for automatic dashboard module registration."""

import importlib.util
import sys
import types
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "flashforge_ac5"


@dataclass
class StaticPathConfig:
    url_path: str
    path: str
    cache_headers: bool


def load_frontend():
    frontend = types.ModuleType("homeassistant.components.frontend")
    frontend.add_extra_js_url = MagicMock()
    http = types.ModuleType("homeassistant.components.http")
    http.StaticPathConfig = StaticPathConfig
    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = type("HomeAssistant", (), {})
    loader = types.ModuleType("homeassistant.loader")
    loader.async_get_integration = AsyncMock(return_value=types.SimpleNamespace(version="1.2.1"))
    const = types.ModuleType("ff_frontend.const")
    const.DOMAIN = "flashforge_ac5"
    stubs = {
        "homeassistant.components.frontend": frontend,
        "homeassistant.components.http": http,
        "homeassistant.core": core,
        "homeassistant.loader": loader,
        "ff_frontend.const": const,
    }
    spec = importlib.util.spec_from_file_location("ff_frontend.frontend", ROOT / "frontend.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


class FrontendTests(unittest.IsolatedAsyncioTestCase):
    async def test_serves_card_before_automatically_loading_it(self):
        module = load_frontend()
        hass = types.SimpleNamespace(
            http=types.SimpleNamespace(async_register_static_paths=AsyncMock())
        )

        async def register(paths):
            module.add_extra_js_url.assert_not_called()
            self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0].url_path, "/flashforge_ac5/flashforge-card.js")
            self.assertEqual(Path(paths[0].path), ROOT / "www" / "flashforge-card.js")
            self.assertTrue(Path(paths[0].path).is_file())
            self.assertFalse(paths[0].cache_headers)

        hass.http.async_register_static_paths.side_effect = register
        await module.async_setup_frontend(hass)
        module.add_extra_js_url.assert_called_once_with(
            hass, "/flashforge_ac5/flashforge-card.js?v=1.2.1"
        )

    async def test_new_integration_version_changes_module_url(self):
        module = load_frontend()
        hass = types.SimpleNamespace(
            http=types.SimpleNamespace(async_register_static_paths=AsyncMock())
        )
        await module.async_setup_frontend(hass)
        first_url = module.add_extra_js_url.call_args.args[1]
        module.async_get_integration.return_value.version = "1.2.2"
        await module.async_setup_frontend(hass)
        self.assertNotEqual(module.add_extra_js_url.call_args.args[1], first_url)

    async def test_registration_failure_does_not_load_a_broken_resource(self):
        module = load_frontend()
        hass = types.SimpleNamespace(
            http=types.SimpleNamespace(
                async_register_static_paths=AsyncMock(side_effect=OSError("cannot register"))
            )
        )
        with self.assertRaisesRegex(OSError, "cannot register"):
            await module.async_setup_frontend(hass)
        module.add_extra_js_url.assert_not_called()
