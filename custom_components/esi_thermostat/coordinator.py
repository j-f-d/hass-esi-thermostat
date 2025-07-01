"""Coordinator for managing ESI thermostat API data and updates."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import logging
import requests

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEVICE_LIST_URL, LOGIN_URL

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
            "device_type": "1,2,4,10,20,23,25",
            "pageSize": 100,
        }

        response = await self.hass.async_add_executor_job(
            lambda: requests.post(DEVICE_LIST_URL, params=params, timeout=15)
        )
        data = response.json()

        if not data.get("statu") or "devices" not in data:
            raise UpdateFailed("Device list fetch failed")

        return data["devices"]
