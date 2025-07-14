"""Coordinator for managing ESI thermostat API data and updates."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ATTR_DEVICE_ID,
    ATTR_DEVICE_TYPE,
    ATTR_TARGET_TEMPERATURE,
    ATTR_WORK_MODE,
    SET_TEMP_URL,
    DEVICE_LIST_URL,
    LOGIN_URL,
    MAX_HIGH_FREQUENCY_POLL_COUNT,
)

_LOGGER = logging.getLogger(__name__)


class ESIDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage ESI API data with configurable update interval."""

    def __init__(
        self,
        hass: HomeAssistant,
        email: str,
        password: str,
        scan_interval_minutes: int,
    ) -> None:
        self._normal_update_interval = timedelta(minutes=scan_interval_minutes)
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="esi_thermostat",
            update_interval=self._normal_update_interval,
        )
        self._email = email
        self._password = password
        self._token: str | None = None
        self._user_id: str | None = None
        self._message_id: int = 1111
        self._update_retry_count: int = 0
        self._device_still_wants_refresh: bool = False

    async def async_request_refresh(self) -> None:
        """Request a refresh."""
        # A device is requesting an update, so decrease the refresh interval
        # to poll more frequently until the state is confirmed or
        # the retry count is exceeded.
        self._update_retry_count: int = MAX_HIGH_FREQUENCY_POLL_COUNT
        self.update_interval = timedelta(seconds=1)
        await super().async_request_refresh()

    async def async_refresh(self) -> None:
        """Refresh data and log errors."""
        # Initially, we assume none of the devices will still want a refresh after this update.
        self._device_still_wants_refresh = False
        if self._update_retry_count >= 1:
            self._update_retry_count -= 1
            if self._update_retry_count == 0:
                # Reset the update interval to the configured value
                super().update_interval = self._normal_update_interval
            return
        await super().async_refresh()
        if not self._device_still_wants_refresh:
            # If no device still needs a refresh, reset the retry count
            self._update_retry_count = 0
            # Reset the update interval to the configured value
            super().update_interval = self._normal_update_interval

    def set_device_still_wants_refresh(self) -> None:
        """Set the flag indicating a device still wants a refresh."""
        self._device_still_wants_refresh = True

    def next_message_id(self) -> str:
        """Increment and return the message ID."""
        self._message_id += 1
        return str(self._message_id)

    async def json(self, response: aiohttp.ClientResponse) -> dict[str, Any]:
        """Parse JSON response from API."""
        if response.status != 200:
            raise ValueError(f"API request failed: {response.status}")
        try:
            # Assume that whatever content type is reported it is valid for JSON parsing
            # this is necessary because as of writing the ESI API uses "text/json;utf-8"
            # instead of the RFC 4627 content-type of "application/json".
            # This is a workaround for the ESI API not using the standard content-type and
            # could be removed if they change to match the RFC, but
            # should still work if they do.
            return await response.json(
                content_type=response.headers.get(
                    "content-type", "application/json"
                ).lower()
            )
        except Exception as err:
            raise UpdateFailed(
                f"ESI API response not recognised as JSON: {err}."
            ) from err

    def get(
        self, valid_device_types: list[str], invalid_device_types: list[str]
    ) -> list[Any]:
        """Get a value from the coordinator data."""
        return [
            device
            for device in self.data.get("devices", [])
            if (
                valid_device_types != []
                and device[ATTR_DEVICE_TYPE] in valid_device_types
            )
            ^ (
                invalid_device_types != []
                and device[ATTR_DEVICE_TYPE] not in invalid_device_types
            )
        ]

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        try:
            if not self._token:
                await self._async_login()

            devices = await self._async_get_devices()

        except Exception as err:
            _LOGGER.exception("Update failed")
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        else:
            return {"devices": devices}

    async def _async_login(self) -> None:
        """Authenticate with ESI API."""
        payload = {"password": self._password, "email": self._email}
        webclient = async_get_clientsession(self.hass)
        async with webclient.post(
            LOGIN_URL,
            data=payload,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as response:
            data = await self.json(response)
        if not data.get("statu") or not data.get("user", {}).get("token"):
            raise UpdateFailed("Login failed")

        self._token = data["user"]["token"]
        self._user_id = str(data["user"].get("id", ""))

    async def _async_get_devices(self) -> list[dict[str, Any]]:
        """Retrieve device list from API."""
        if not self._token:
            raise ValueError("No auth token")

        params = {
            "user_id": self._user_id,
            "token": self._token,
            # Device types (other than 1) from https://github.com/josh-taylor/esi
            ATTR_DEVICE_TYPE: "1,2,4,10,20,23,25",
            "pageSize": 100,
        }

        webclient = async_get_clientsession(self.hass)
        async with webclient.post(
            DEVICE_LIST_URL,
            params=params,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as response:
            data = await self.json(response)

        if not data.get("statu") or "devices" not in data:
            raise UpdateFailed("Device list fetch failed")

        return data["devices"]

    async def async_set_work_mode(
        self, device_id: str, work_mode: int, temperature: int
    ) -> None:
        """Set the thermostat work mode via API."""
        if not self._token:
            raise ValueError("No auth token")

        params = {
            "user_id": self._user_id,
            "token": self._token,
            "messageId": self.next_message_id(),  # Message ID doesn't seem to matter, maybe an incremental ID would be better?
            ATTR_DEVICE_ID: device_id,
            ATTR_WORK_MODE: str(work_mode),
            ATTR_TARGET_TEMPERATURE: temperature,
        }

        webclient = async_get_clientsession(self.hass)
        async with webclient.post(
            SET_TEMP_URL,
            params=params,
            timeout=aiohttp.ClientTimeout(total=5),
        ) as response:
            data = await self.json(response)

        if not data.get("statu"):
            error_msg = data.get("message", "Unknown error")
            error_code = data.get("error_code")

            if error_code == 7:
                _LOGGER.error("Work mode change rejected: %s", error_msg)
            _LOGGER.error("API error: %s\n", params["work_mode"])

    def available(self) -> bool:
        """Check if this coordinator is available."""
        return self._token is not None
