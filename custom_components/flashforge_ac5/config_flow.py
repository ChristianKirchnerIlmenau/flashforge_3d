"""Config and options flow for the FlashForge integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .api import (
    FlashForgeApi,
    FlashForgeApiError,
    FlashForgeAuthError,
    FlashForgeConnectionError,
)
from .const import (
    CONF_CHECK_CODE,
    CONF_SERIAL_NUMBER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_SERIAL_NUMBER): str,
        vol.Required(CONF_CHECK_CODE): str,
        vol.Optional(CONF_NAME): str,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CHECK_CODE): str,
        vol.Required("scan_interval", default=DEFAULT_SCAN_INTERVAL): vol.All(
            cv.positive_int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
        ),
    }
)


class FlashForgeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a FlashForge printer."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect connection details and verify them against the printer."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            serial = user_input[CONF_SERIAL_NUMBER].strip()
            check_code = user_input[CONF_CHECK_CODE].strip()

            await self.async_set_unique_id(serial)
            self._abort_if_unique_id_configured(updates={CONF_HOST: host})

            api = FlashForgeApi(host, serial, check_code)
            try:
                info = await api.async_connect()
            except FlashForgeAuthError:
                errors["base"] = "invalid_auth"
            except FlashForgeConnectionError:
                errors["base"] = "cannot_connect"
            except FlashForgeApiError:
                errors["base"] = "unknown"
            except Exception:
                _LOGGER.exception("Unexpected error while validating the printer")
                errors["base"] = "unknown"
            else:
                title = user_input.get(CONF_NAME) or info.name or host
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_HOST: host,
                        CONF_SERIAL_NUMBER: serial,
                        CONF_CHECK_CODE: check_code,
                    },
                )
            finally:
                await api.async_dispose()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input or {}
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow changing host / credentials of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            serial = user_input[CONF_SERIAL_NUMBER].strip()
            check_code = user_input[CONF_CHECK_CODE].strip()

            api = FlashForgeApi(host, serial, check_code)
            try:
                await api.async_connect()
            except FlashForgeAuthError:
                errors["base"] = "invalid_auth"
            except FlashForgeConnectionError:
                errors["base"] = "cannot_connect"
            except FlashForgeApiError:
                errors["base"] = "unknown"
            else:
                # The serial number is the identity of the entry, so a changed
                # serial must not silently create a second entry.
                if serial != entry.unique_id:
                    await self.async_set_unique_id(serial)
                    self._abort_if_unique_id_configured(updates={CONF_HOST: host})

                # ``reason`` defaults to ``reconfigure_successful`` when the
                # flow source is a reconfigure flow.
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_HOST: host,
                        CONF_SERIAL_NUMBER: serial,
                        CONF_CHECK_CODE: check_code,
                    },
                )
            finally:
                await api.async_dispose()

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, {**entry.data, **(user_input or {})}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler.

        The entry is read from ``OptionsFlow.config_entry`` instead of being
        stored here: keeping a copy is deprecated in current HA releases.
        """
        return FlashForgeOptionsFlow()


class FlashForgeOptionsFlow(OptionsFlow):
    """Tune polling interval and rotate the check code."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and store the options."""
        entry = self.config_entry

        if user_input is not None:
            data = dict(entry.data)
            if user_input.get(CONF_CHECK_CODE):
                data[CONF_CHECK_CODE] = user_input[CONF_CHECK_CODE].strip()
            self.hass.config_entries.async_update_entry(entry, data=data)
            return self.async_create_entry(
                data={"scan_interval": user_input["scan_interval"]}
            )

        current_interval = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, {"scan_interval": current_interval}
            ),
        )
