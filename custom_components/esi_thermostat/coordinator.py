"""Coordinator for managing ESI thermostat API data and updates."""

from datetime import timedelta
import logging
from typing import Any

from esi_controls_async import (
    ESICentroAPI,
    ESIDevice,
    ESIDeviceListError,
    ESINoAuthorization,
    ESISetCommandError,
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import MAX_HIGH_FREQUENCY_POLL_COUNT

_LOGGER = logging.getLogger(__name__)


class ESIDataUpdateCoordinator(DataUpdateCoordinator[dict[str,list[ESIDevice]|None]]):
    """Class to manage ESI API data with configurable update interval."""

    def __init__(
        self,
        hass: HomeAssistant,
        email: str,
        password: str,
        scan_interval_minutes: int,
    ) -> None:
        """Initialize coordinator."""
        self._normal_update_interval = timedelta(minutes=scan_interval_minutes)
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name="esi_thermostat",
            update_interval=self._normal_update_interval,
        )
        self._email = email
        self._password = password
        self._esi = ESICentroAPI(session=async_get_clientsession(hass))
        self._update_retry_count: int = 0
        self._short_update_interval = timedelta(seconds=1)
        # When a device needs a refresh, this is set true and when an
        # update happens, it will be set false, but a device can call
        # set_device_still_wants_refresh from its _handle_coordinator_update
        # function to keep polling.
        self._device_still_wants_refresh: bool = False

    async def async_request_refresh(self) -> None:
        """Request a refresh."""
        # A device is requesting an update, so decrease the refresh interval
        # to poll more frequently until the state is confirmed or
        # the retry count is exceeded.
        self._update_retry_count = MAX_HIGH_FREQUENCY_POLL_COUNT
        self.update_interval = self._short_update_interval
        await super().async_request_refresh()

    async def _async_refresh(
        self,
        log_failures: bool = True,
        raise_on_auth_failed: bool = False,
        scheduled: bool = False,
        raise_on_entry_error: bool = False,
    ) -> None:
        """Refresh data and log errors."""
        # Initially, we assume none of the devices will still want a refresh after this update.
        self._device_still_wants_refresh = False
        self._update_retry_count -= 1
        if self._update_retry_count <= 0:
            # Reset the update interval to the configured value
            self.update_interval = self._normal_update_interval
        await super()._async_refresh(
            log_failures, raise_on_auth_failed, scheduled, raise_on_entry_error
        )
        if not self._device_still_wants_refresh:
            # If no device still needs a refresh, reset the retry count
            self._update_retry_count = 0
            # Reset the update interval to the configured value
            self.update_interval = self._normal_update_interval

    def set_device_still_wants_refresh(self) -> None:
        """Set the flag indicating a device still wants a refresh."""
        self._device_still_wants_refresh = True

    def get(self, valid_device_types: set, invalid_device_types: set) -> list[ESIDevice|None]:
        """Get a value from the coordinator data."""

        def allowed(key: str|None, valid_set: set, invalid_set: set) -> bool:
            if valid_set and key not in valid_set:
                return False
            if invalid_set and key in invalid_set:
                return False
            return True

        devices = self.data.get("devices", [])
        if devices is None:
            return []
        return [
            device
            for device in devices
            if (allowed(device.device_type, valid_device_types, invalid_device_types))
        ]

    async def _async_login(self) -> None:
        """Authenticate with ESI API."""
        await self._esi.login(email=self._email, password=self._password)
        if not self._esi.available():
            raise UpdateFailed("Login failed")

    async def _async_update_data(self) -> dict[str,list[ESIDevice]|None]:
        """Retrieve device list from API."""
        if not self._esi.available():
            await self._async_login()

        try:
            await self._esi.async_update_devices()
        except ESINoAuthorization as exc:
            raise UpdateFailed("No Authorization") from exc
        except ESIDeviceListError as exc:
            raise UpdateFailed("Device list fetch failed") from exc

        raw_devs = self._esi.get_devices()
        if raw_devs is None:
            return {"devices": None}
        return {"devices": [ESIDevice(raw_data=d, api=self._esi) for d in raw_devs]}

    async def async_set_work_mode(
        self, device_id: str, work_mode: int, temperature: float
    ) -> None:
        """Set the thermostat work mode via API."""
        if not self._esi.available():
            await self._async_login()

        try:
            await self._esi.async_set_work_mode(
                device_id=device_id, work_mode=work_mode, temperature=temperature
            )
        except ESINoAuthorization as exc:
            raise UpdateFailed("No Authorization") from exc
        except ESISetCommandError as exc:
            raise UpdateFailed("Work mode rejected") from exc

    def available(self) -> bool:
        """Check if this coordinator is available."""
        return self._esi.available()
