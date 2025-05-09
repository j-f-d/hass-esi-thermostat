"""Config flow for ESI Thermostat integration."""
from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL_MINUTES,
)


class ESIThermostatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ESI Thermostat."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate credentials (replace with real validation)
            valid = await self._test_credentials(
                user_input[CONF_EMAIL],
                user_input[CONF_PASSWORD]
            )
            
            if valid:
                options = {
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL]
                }
                
                return self.async_create_entry(
                    title=DEFAULT_NAME,
                    data={
                        CONF_EMAIL: user_input[CONF_EMAIL],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                    options=options,
                )
            errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=DEFAULT_SCAN_INTERVAL_MINUTES
                ): cv.positive_int,
            }),
            errors=errors,
        )

    async def _test_credentials(self, email: str, password: str) -> bool:
        """Test if the provided credentials are valid."""
        # TODO: Replace with actual API call
        return True

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ESIThermostatOptionsFlow:
        """Get the options flow for this handler."""
        return ESIThermostatOptionsFlow(config_entry)


class ESIThermostatOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for ESI Thermostat."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        super().__init__()
        # Use a safe attribute name to avoid conflict with HA internals
        self._entry_id_safe = config_entry.entry_id

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""

        entry = self.hass.config_entries.async_get_entry(self._entry_id_safe)

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = entry.options.get(
            CONF_SCAN_INTERVAL,
            DEFAULT_SCAN_INTERVAL_MINUTES
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=current_interval
                ): cv.positive_int,
            }),
        )
