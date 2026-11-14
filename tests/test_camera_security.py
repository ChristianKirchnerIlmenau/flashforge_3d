"""Regression tests for the camera's network trust boundary."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "flashforge_ac5"


def load_modules():
    """Load the integration modules with lightweight external dependency stubs."""
    aiohttp = types.ModuleType("aiohttp")
    aiohttp.ClientError = type("ClientError", (Exception,), {})
    aiohttp.ClientTimeout = MagicMock()
    aiohttp.ClientSession = MagicMock()
    aiohttp.web = types.ModuleType("aiohttp.web")

    flashforge = types.ModuleType("flashforge")
    flashforge.FlashForgeClient = MagicMock()
    exceptions = types.ModuleType("flashforge.exceptions")
    exceptions.FlashForgeError = type("FlashForgeError", (Exception,), {})
    models = types.ModuleType("flashforge.models")
    models.FFMachineInfo = type("FFMachineInfo", (), {})

    camera = types.ModuleType("homeassistant.components.camera")
    camera.Camera = type("Camera", (), {})
    entries = types.ModuleType("homeassistant.config_entries")
    entries.ConfigEntry = type("ConfigEntry", (), {})
    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = type("HomeAssistant", (), {})
    client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    client.async_get_clientsession = MagicMock()
    platform = types.ModuleType("homeassistant.helpers.entity_platform")
    platform.AddEntitiesCallback = type("AddEntitiesCallback", (), {})
    coordinator = types.ModuleType("ff_security.coordinator")
    coordinator.FlashForgeDataUpdateCoordinator = type("FlashForgeDataUpdateCoordinator", (), {})
    entity = types.ModuleType("ff_security.entity")
    entity.FlashForgeEntity = type("FlashForgeEntity", (), {})

    stubs = {
        "aiohttp": aiohttp,
        "flashforge": flashforge,
        "flashforge.exceptions": exceptions,
        "flashforge.models": models,
        "homeassistant.components.camera": camera,
        "homeassistant.config_entries": entries,
        "homeassistant.core": core,
        "homeassistant.helpers.aiohttp_client": client,
        "homeassistant.helpers.entity_platform": platform,
        "ff_security.coordinator": coordinator,
        "ff_security.entity": entity,
    }

    def load(name, file):
        spec = importlib.util.spec_from_file_location(name, ROOT / file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    with patch.dict(sys.modules, stubs):
        api = load("ff_security.api", "api.py")
        with patch.dict(sys.modules, {"ff_security.api": api}):
            return api, load("ff_security.camera", "camera.py")


api_module, camera_module = load_modules()


class Response:
    def __init__(self, status, content_type=""):
        self.status = status
        self.headers = {"Content-Type": content_type}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class CameraSecurityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.api = api_module.FlashForgeApi("printer.local", "serial", "code")
        self.url = "http://printer.local:8080/?action=stream"

    async def test_reported_url_must_match_the_printer_endpoint(self):
        good = types.SimpleNamespace(camera_stream_url=self.url, has_camera=True)
        self.assertEqual(await self.api.async_resolve_camera_url(good), self.url)

        for url in (
            "http://other.local:8080/?action=stream",
            "http://printer.local:8898/?action=stream",
            "http://printer.local:8080/admin",
            "https://printer.local:8080/?action=stream",
            "http://printer.local@other.local:8080/?action=stream",
            "http://user@printer.local:8080/?action=stream",
            "http://printer.local:bad/?action=stream",
            "http://printer.local:8080/?action=stream#fragment",
        ):
            with self.subTest(url=url):
                info = types.SimpleNamespace(camera_stream_url=url, has_camera=True)
                self.assertEqual(await self.api.async_resolve_camera_url(info), self.url)
                self.assertEqual(self.api.cached_camera_url(), self.url)

    async def test_untrusted_url_is_not_used_when_cache_is_empty(self):
        info = types.SimpleNamespace(
            camera_stream_url="http://other.local:8080/?action=stream", has_camera=True
        )
        self.assertEqual(await self.api.async_resolve_camera_url(info), "")

    async def test_probe_rejects_redirects_for_head_and_get(self):
        session = MagicMock()
        session.__aenter__.return_value = session
        session.head.return_value = Response(302)
        session.get.return_value = Response(302)
        with patch.object(api_module.aiohttp, "ClientSession", return_value=session):
            self.assertFalse(await self.api._async_probe_camera())
        for method in (session.head, session.get):
            self.assertEqual(method.call_args.args[0], self.url)
            self.assertIs(method.call_args.kwargs["allow_redirects"], False)

    async def test_probe_accepts_oem_stream_after_head_fails(self):
        session = MagicMock()
        session.__aenter__.return_value = session
        session.head.return_value = Response(405)
        session.get.return_value = Response(200, "multipart/x-mixed-replace; boundary=frame")
        with patch.object(api_module.aiohttp, "ClientSession", return_value=session):
            result = await self.api.async_resolve_camera_url(None, probe=True)
        self.assertEqual(result, self.url)

    async def test_stream_and_snapshot_do_not_follow_redirects(self):
        session = MagicMock()
        session.get.return_value = Response(302)
        reader = camera_module._MjpegFrameReader(session, self.url)
        await reader._async_read()
        self.assertIs(session.get.call_args.kwargs["allow_redirects"], False)

        camera = object.__new__(camera_module.FlashForgeCamera)
        camera.runtime_data = types.SimpleNamespace(api=self.api)
        camera.hass = object()
        with patch.object(camera_module, "async_get_clientsession", return_value=session):
            self.assertIsNone(await camera._async_snapshot())
        self.assertIs(session.get.call_args.kwargs["allow_redirects"], False)
        self.assertEqual(session.get.call_args.args[0], "http://printer.local:8080/?action=snapshot")


if __name__ == "__main__":
    unittest.main()
