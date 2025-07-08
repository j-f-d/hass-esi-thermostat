"""Coordinator for managing ESI thermostat API data and updates."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import requests

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ATTR_DEVICE_ID,
    ATTR_DEVICE_TYPE,
    ATTR_TARGET_TEMPERATURE,
    ATTR_WORK_MODE,
    SET_TEMP_URL,
    DEVICE_LIST_URL,
    LOGIN_URL,
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
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="esi_thermostat",
            update_interval=timedelta(minutes=scan_interval_minutes),
        )
        self.email = email
        self.password = password
        self.token: str | None = None
        self.user_id: str | None = None
        self.message_id: int = 1111

    def next_message_id(self) -> str:
        """Increment and return the message ID."""
        self.message_id += 1
        return str(self.message_id)

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
            if not self.token:
                await self._async_login()

            devices = await self._async_get_devices()

        except Exception as err:
            _LOGGER.exception("Update failed")
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        else:
            return {"devices": devices}

    async def _async_login(self) -> None:
        """Authenticate with ESI API."""
        payload = {"password": self.password, "email": self.email}

        response = await self.hass.async_add_executor_job(
            lambda: requests.post(LOGIN_URL, data=payload, timeout=15)
        )
        data = response.json()

        if not data.get("statu") or not data.get("user", {}).get("token"):
            raise UpdateFailed("Login failed")

        self.token = data["user"]["token"]
        self.user_id = str(data["user"].get("id", ""))

    async def _async_get_devices(self) -> list[dict[str, Any]]:
        """Retrieve device list from API."""
        params = {
            "user_id": self.user_id,
            "token": self.token,
            # Device types (other than 1) from https://github.com/josh-taylor/esi
            ATTR_DEVICE_TYPE: "1,2,4,10,20,23,25",
            "pageSize": 100,
        }

        response = await self.hass.async_add_executor_job(
            lambda: requests.post(DEVICE_LIST_URL, params=params, timeout=15)
        )
        data = response.json()

        if not data.get("statu") or "devices" not in data:
            raise UpdateFailed("Device list fetch failed")

        return data["devices"]

    async def async_set_work_mode(
        self, device_id: str, work_mode: int, temperature: int
    ) -> None:
        """Set the thermostat work mode via API."""
        await self.hass.async_add_executor_job(
            self._set_work_mode, device_id, work_mode, temperature
        )

    def _set_work_mode(self, device_id: str, work_mode: int, temperature: int) -> None:
        """Set the thermostat work mode via API."""
        if not self.token:
            raise ValueError("No auth token")

        params = {
            "user_id": self.user_id,
            "token": self.token,
            "messageId": self.next_message_id(),  # Message ID doesn't seem to matter, maybe an incremental ID would be better?
            ATTR_DEVICE_ID: device_id,
            ATTR_WORK_MODE: str(work_mode),
            ATTR_TARGET_TEMPERATURE: temperature,
        }

        try:
            response = requests.post(SET_TEMP_URL, params=params, timeout=5)
            response.raise_for_status()
            response_data = response.json()
        except Exception as err:
            raise ValueError(f"API request failed: {err}") from err

        if not response_data.get("statu"):
            error_msg = response_data.get("message", "Unknown error")
            error_code = response_data.get("error_code")

            if error_code == 7:
                _LOGGER.error("Work mode change rejected: %s", error_msg)
            _LOGGER.error("API error: %s\n", params["work_mode"])
