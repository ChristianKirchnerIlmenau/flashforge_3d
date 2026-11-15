"""Tests for manually enabling the printer light switch."""

import importlib.util
import sys
import types
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from test_camera_security import api_module


@dataclass(frozen=True, kw_only=True)
class SwitchEntityDescription:
    key: str
    translation_key: str
    device_class: object
    icon: str


@dataclass(frozen=True, kw_only=True)
class BinarySensorEntityDescription:
    key: str
    translation_key: str
    icon: str
    device_class: object = None


class FlashForgeEntity:
    def __init__(self, coordinator, entry, unique_suffix):
        self.coordinator = coordinator
        self.entry = entry
        self.unique_suffix = unique_suffix
        self.runtime_data = entry.runtime_data

    @property
    def snapshot(self):
        return self.coordinator.data

    @property
    def available(self):
        return True


def load_switch_module():
    vol = types.ModuleType("voluptuous")
    vol.Schema = lambda schema: schema
    vol.Required = lambda key, **kwargs: key
    vol.Optional = lambda key, **kwargs: key
    vol.All = lambda *args: args
    vol.Range = lambda **kwargs: kwargs
    switch = types.ModuleType("homeassistant.components.switch")
    switch.SwitchDeviceClass = types.SimpleNamespace(SWITCH="switch")
    switch.SwitchEntity = type("SwitchEntity", (), {})
    switch.SwitchEntityDescription = SwitchEntityDescription
    binary_sensor = types.ModuleType("homeassistant.components.binary_sensor")
    binary_sensor.BinarySensorDeviceClass = types.SimpleNamespace(
        RUNNING="running", DOOR="door", PROBLEM="problem"
    )
    binary_sensor.BinarySensorEntity = type("BinarySensorEntity", (), {})
    binary_sensor.BinarySensorEntityDescription = BinarySensorEntityDescription
    entries = types.ModuleType("homeassistant.config_entries")
    entries.ConfigEntry = type("ConfigEntry", (), {})
    entries.ConfigFlow = type(
        "ConfigFlow", (), {"__init_subclass__": classmethod(lambda cls, **kwargs: None)}
    )
    entries.ConfigFlowResult = dict
    entries.OptionsFlow = type("OptionsFlow", (), {})
    ha_const = types.ModuleType("homeassistant.const")
    ha_const.CONF_HOST = "host"
    ha_const.CONF_NAME = "name"
    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = type("HomeAssistant", (), {})
    core.callback = lambda func: func
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.config_validation = types.SimpleNamespace(positive_int=int)
    exceptions = types.ModuleType("homeassistant.exceptions")
    exceptions.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
    platform = types.ModuleType("homeassistant.helpers.entity_platform")
    platform.AddEntitiesCallback = type("AddEntitiesCallback", (), {})
    api = types.ModuleType("ff_light.api")
    api.FlashForgeApi = type("FlashForgeApi", (), {})
    api.FlashForgeApiError = type("FlashForgeApiError", (Exception,), {})
    api.FlashForgeAuthError = type("FlashForgeAuthError", (Exception,), {})
    api.FlashForgeConnectionError = type("FlashForgeConnectionError", (Exception,), {})
    const = types.ModuleType("ff_light.const")
    const.CONF_FORCE_LED_CONTROL = "force_led_control"
    const.CONF_CHECK_CODE = "check_code"
    const.CONF_SERIAL_NUMBER = "serial_number"
    const.DEFAULT_SCAN_INTERVAL = 20
    const.MIN_SCAN_INTERVAL = 5
    const.MAX_SCAN_INTERVAL = 300
    const.DOMAIN = "flashforge_ac5"
    coordinator = types.ModuleType("ff_light.coordinator")
    coordinator.FlashForgeDataUpdateCoordinator = type("FlashForgeDataUpdateCoordinator", (), {})
    entity = types.ModuleType("ff_light.entity")
    entity.FlashForgeEntity = FlashForgeEntity
    models = types.ModuleType("ff_light.models")
    models.PrinterSnapshot = type("PrinterSnapshot", (), {})
    stubs = {
        "voluptuous": vol,
        "homeassistant.components.switch": switch,
        "homeassistant.components.binary_sensor": binary_sensor,
        "homeassistant.config_entries": entries,
        "homeassistant.const": ha_const,
        "homeassistant.core": core,
        "homeassistant.exceptions": exceptions,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.entity_platform": platform,
        "ff_light.api": api,
        "ff_light.const": const,
        "ff_light.coordinator": coordinator,
        "ff_light.entity": entity,
        "ff_light.models": models,
    }
    root = Path(__file__).resolve().parents[1] / "custom_components/flashforge_ac5"
    with patch.dict(sys.modules, stubs):
        modules = []
        for name in ("switch", "binary_sensor", "config_flow"):
            spec = importlib.util.spec_from_file_location(f"ff_light.{name}", root / f"{name}.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            modules.append(module)
    return modules


switch_module, binary_sensor_module, config_flow_module = load_switch_module()


class LightSwitchTests(unittest.IsolatedAsyncioTestCase):
    async def setup_switch(self, *, detected, force):
        client = MagicMock()
        client.led_control = detected
        client.filtration_control = False
        client.control.set_led_on = AsyncMock(return_value=True)
        client.control.set_led_off = AsyncMock(return_value=True)
        client.set_feature_overrides.side_effect = lambda **kwargs: setattr(
            client, "led_control", kwargs["led_control"]
        )
        with patch.object(api_module, "FlashForgeClient", return_value=client):
            api = api_module.FlashForgeApi(
                "printer.local", "serial", "code", force_led_control=force
            )
        coordinator = types.SimpleNamespace(
            api=api,
            data=types.SimpleNamespace(info=types.SimpleNamespace(lights_on=False)),
            async_request_refresh=AsyncMock(),
        )
        entry = types.SimpleNamespace(
            options={"force_led_control": force},
            runtime_data=types.SimpleNamespace(coordinator=coordinator, api=api),
        )
        add_entities = MagicMock()
        await switch_module.async_setup_entry(None, entry, add_entities)
        add_sensors = MagicMock()
        await binary_sensor_module.async_setup_entry(None, entry, add_sensors)
        sensors = list(add_sensors.call_args.args[0])
        light_sensors = [sensor for sensor in sensors if sensor.unique_suffix == "light_status"]
        return client, coordinator, add_entities.call_args.args[0], light_sensors

    async def test_override_exposes_and_controls_unreported_light(self):
        client, coordinator, entities, sensors = await self.setup_switch(detected=False, force=True)
        client.set_feature_overrides.assert_called_once_with(led_control=True)
        self.assertEqual(len(entities), 1)
        light = entities[0]
        self.assertEqual(light.unique_suffix, "led")
        self.assertFalse(light.is_on)
        self.assertEqual(len(sensors), 1)
        self.assertFalse(sensors[0].is_on)
        coordinator.data.info.lights_on = True
        self.assertTrue(light.is_on)
        self.assertTrue(sensors[0].is_on)
        await light.async_turn_on()
        client.control.set_led_on.assert_awaited_once()
        await light.async_turn_off()
        client.control.set_led_off.assert_awaited_once()
        self.assertEqual(coordinator.async_request_refresh.await_count, 2)

    async def test_default_preserves_automatic_capability_detection(self):
        for detected in (False, True):
            with self.subTest(detected=detected):
                client, _, entities, sensors = await self.setup_switch(detected=detected, force=False)
                client.set_feature_overrides.assert_not_called()
                self.assertEqual(len(entities), int(detected))
                self.assertEqual(len(sensors), int(detected))

    async def test_rejected_command_reports_error(self):
        client, coordinator, entities, _ = await self.setup_switch(detected=False, force=True)
        client.control.set_led_on.return_value = False
        with self.assertRaises(switch_module.HomeAssistantError):
            await entities[0].async_turn_on()
        coordinator.async_request_refresh.assert_not_awaited()

    async def test_options_restore_and_save_light_setting(self):
        flow = config_flow_module.FlashForgeOptionsFlow()
        flow.config_entry = types.SimpleNamespace(
            data={"check_code": "code"},
            options={"scan_interval": 30, "force_led_control": True},
        )
        flow.hass = types.SimpleNamespace(config_entries=types.SimpleNamespace(
            async_update_entry=MagicMock()
        ))
        flow.add_suggested_values_to_schema = MagicMock(return_value="schema")
        flow.async_show_form = MagicMock()
        flow.async_create_entry = MagicMock()
        await flow.async_step_init()
        self.assertEqual(
            flow.add_suggested_values_to_schema.call_args.args[1],
            {"scan_interval": 30, "force_led_control": True},
        )
        await flow.async_step_init({"scan_interval": 30, "force_led_control": False})
        flow.async_create_entry.assert_called_once_with(
            data={"scan_interval": 30, "force_led_control": False}
        )
        flow.hass.config_entries.async_update_entry.assert_called_once_with(
            flow.config_entry, data={"check_code": "code"}
        )


if __name__ == "__main__":
    unittest.main()
