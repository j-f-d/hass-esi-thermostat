"""Config flow for ESI Thermostat integration."""

import logging
from typing import Any

import aiohttp
from esi_controls_async import ESICentroAPI
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class ESIThermostatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ESI Thermostat."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                valid = await self._test_credentials(
                    user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
                )

                if valid:
                    # Set the unique ID as the email address
                    await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
                    # This will prevent re-adding the same account
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=DEFAULT_NAME,
                        data={
                            CONF_EMAIL: user_input[CONF_EMAIL],
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                        },
                        options={
                            CONF_SCAN_INTERVAL: user_input.get(
                                CONF_SCAN_INTERVAL,
                                DEFAULT_SCAN_INTERVAL_MINUTES,
                            )
                        },
                    )
                errors["base"] = "incorrect_email_or_password"

            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL_MINUTES
                    ): cv.positive_int,
                }
            ),
            errors=errors,
        )

    async def _test_credentials(self, email: str, password: str) -> bool:
        """Test if the provided credentials are valid."""
        esi = ESICentroAPI(session=async_get_clientsession(self.hass))
        await esi.login(email=email, password=password)
        return esi.available()

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for handler."""
        return ESIThermostatOptionsFlow()


class ESIThermostatOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for ESI Thermostat."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES
                        ),
                    ): cv.positive_int,
                }
            ),
        )
