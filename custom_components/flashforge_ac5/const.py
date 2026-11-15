"""Constants for the FlashForge 3D Printer integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "flashforge_ac5"
MANUFACTURER = "FlashForge"

CONF_SERIAL_NUMBER = "serial_number"
CONF_CHECK_CODE = "check_code"
CONF_FORCE_LED_CONTROL = "force_led_control"

DEFAULT_SCAN_INTERVAL = 20
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 300

# How often (in failed probes) the camera stream URL is re-detected while the
# printer has not yet reported one.
CAMERA_PROBE_RETRY_CYCLES = 10

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.SENSOR,
    Platform.SWITCH,
]

DEFAULT_SCAN_INTERVAL_TIMEDELTA = timedelta(seconds=DEFAULT_SCAN_INTERVAL)
