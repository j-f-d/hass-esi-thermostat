"""ESI Thermostat Climate Platform."""

import asyncio
import contextlib
from enum import IntEnum
import logging
from typing import Any, cast, Final

from esi_controls_async import ESIDevice

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEFAULT_NAME,
    DEVICE_TYPES_WATERHEATER, # For ignored devices (non-climate).
    DOMAIN,
    WATERHEATER_TH_WORK_HEATING,
)
from .coordinator import ESIDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# We should probably allow this to be set in the API.
DEFAULT_MANUAL_TEMPERATURE: Final = 20.0

class ClimateWorkMode(IntEnum):
    AUTO = 0
    AUTO_TEMP_OVERRIDE = 1
    ALL_DAY = 2
    BOOST = 3
    OFF = 4
    MANUAL = 5
    HOLIDAY = 6
    OFF_BOOST = 7
    HOLIDAY_BOOST = 8
    MANUAL_BOOST = 9



async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize climate platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    if not coordinator.data:
        await coordinator.async_config_entry_first_refresh()

    entities: list[ClimateEntity] = []
    # It would be better to just get climate devices, but I don't know what the
    # device type(s) are for climate devices, so just exclude the water heater types,
    # since there is a class to handle them explicitly, but nothing else currently.
    for device in coordinator.get(set([]), set(DEVICE_TYPES_WATERHEATER)):
        try:
            entities.append(
                EsiClimate(
                    coordinator=coordinator,
                    device_id=device.device_id,
                    name=device.device_name                )
            )
        except KeyError:
            continue

    if entities:
        async_add_entities(entities)


class EsiClimate(CoordinatorEntity, ClimateEntity):
    """ESI Climate Entity."""

    _attr_has_entity_name = False
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.AUTO, HVACMode.OFF]
    _attr_min_temp = 5.0
    _attr_max_temp = 35.0
    _attr_target_temperature_step = 0.5

    WORK_MODE_TO_HVAC: dict[ClimateWorkMode | None, HVACMode | None] = {
        None: None,
        ClimateWorkMode.MANUAL: HVACMode.HEAT,
        ClimateWorkMode.AUTO: HVACMode.AUTO,
        ClimateWorkMode.AUTO_TEMP_OVERRIDE: HVACMode.AUTO,
        ClimateWorkMode.OFF: HVACMode.OFF,
    }

    HVAC_TO_WORK_MODE: dict[HVACMode, ClimateWorkMode] = {
        HVACMode.HEAT: ClimateWorkMode.MANUAL,
        HVACMode.AUTO: ClimateWorkMode.AUTO,
        HVACMode.OFF: ClimateWorkMode.OFF,
    }

    def __init__(
        self, coordinator: ESIDataUpdateCoordinator, device_id: str, name: str | None = DEFAULT_NAME
    ) -> None:
        """Initialize the ESI Thermostat entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{device_id}"
        self._attr_hvac_mode = None
        self._attr_target_temperature

        # Last known server-confirmed state, all none for now, but
        # will be filled out first update.
        self._last_current_temp: float | None = None
        self._last_confirmed_target_temp: float | None = None
        self._last_confirmed_work_mode: ClimateWorkMode | None = None

        # Pending state that hasn't been confirmed by server
        self._pending_target_temp = None
        self._pending_work_mode = None

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=name,
            manufacturer="ESI Heating",
            model="Smart Thermostat",
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        # Set pending state immediately
        if hvac_mode == HVACMode.OFF:
            self._pending_target_temp = self._attr_min_temp
        self._pending_work_mode = self.HVAC_TO_WORK_MODE.get(hvac_mode, None)

        # Request update to server
        await self._async_perform_update()

    async def async_set_temperature(self, **kwargs) -> None:
        """Set the target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        if self._last_confirmed_work_mode == ClimateWorkMode.AUTO:
            # Setting temperature will require manual mode
            self._pending_work_mode = ClimateWorkMode.AUTO_TEMP_OVERRIDE
        else:
            # Setting temperature will require manual mode
            self._pending_work_mode = ClimateWorkMode.MANUAL
        self._pending_target_temp = temperature

        # Request update to server
        await self._async_perform_update()

    async def _async_perform_update(self) -> None:
        """Perform the actual thermostat update."""

        try:
            # Whichever function calls this one, it must have set
            # _pending_work_mode and may have set _pending_target_temp
            target_temp = self._pending_target_temp

            # The caller didn't set work mode, we'll ignore them
            if self._pending_work_mode is None:
                self._pending_target_temp = None
                # Just request an update if no work mode is set, to ensure state is up to date
                await self.coordinator.async_request_refresh()
                return

            # Validate the temperature
            target_temp = (
                    self._pending_target_temp
                    or self._last_confirmed_target_temp
                    or self.target_temperature
                    or self.current_temperature
                    or DEFAULT_MANUAL_TEMPERATURE
                )

            # Send request to server
            await cast(ESIDataUpdateCoordinator, self.coordinator).async_set_work_mode(
                self._device_id, self._pending_work_mode, target_temp
            )

            # Refresh coordinator to get latest state
            await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.exception("Update failed: %s", err)

            # On failure, clear pending state
            self._pending_target_temp = None
            self._pending_work_mode = None

            # Refresh to get current server state
            await self.coordinator.async_request_refresh()

    def _set_hvac_action(self) -> None:
        """Set the HVAC action attribute based on the th_work field."""
        if self._attr_hvac_mode == HVACMode.OFF:
            self._attr_hvac_action = HVACAction.OFF
        else:
            device = self._get_device()
            if device and device.th_work and device.th_work == WATERHEATER_TH_WORK_HEATING:
                self._attr_hvac_action = HVACAction.HEATING
            self._attr_hvac_action = HVACAction.IDLE

    def _handle_coordinator_update(self) -> None:
        device: ESIDevice | None = self._get_device()
        if device is None:
            super()._handle_coordinator_update()
            return

        # First update the work mode and corresponding hvac_mode and hvac_action
        try:
            device_work_mode = device.work_mode
            if device_work_mode is not None:
                self._last_confirmed_work_mode = ClimateWorkMode(device_work_mode)
        except (ValueError, TypeError, KeyError):
            _LOGGER.error(
                "Failed to parse work mode for device %s",
                self._device_id,
            )
        # Try to set the current hvac_mode, which needs to be one of the values specified in
        # _attr_hvac_modes, or None.
        self._attr_hvac_mode = self.WORK_MODE_TO_HVAC.get(self._last_confirmed_work_mode, None)
        if self._attr_hvac_mode == HVACMode.OFF:
            self._attr_hvac_action = HVACAction.OFF
        else:
            if device.th_work == "1":
                self._attr_hvac_action = HVACAction.HEATING
            self._attr_hvac_action = HVACAction.IDLE

        # Update current temperature
        try:
            self._attr_current_temperature = device.measured_temperature
            if self._attr_current_temperature is not None:
                self._last_confirmed_temp = device.measured_temperature
        except (TypeError, ValueError, KeyError):
            _LOGGER.error(
                "Failed to parse current temperature for device %s",
                self._device_id,
            )

        # Until there is a confirmed target temperature, try to use the device's reported target temperature
        device_target_temp = None
        try:
            device_target_temp = device.target_temperature
        except (TypeError, ValueError, KeyError):
            _LOGGER.error(
                "Failed to parse target temperature for device %s",
                self._device_id,
            )
        if self._last_confirmed_target_temp is None:
            self._last_confirmed_target_temp = device_target_temp
        if (
            self._pending_work_mode is None
            or self._pending_work_mode == self._last_confirmed_work_mode
        ) and self._last_confirmed_work_mode is not ClimateWorkMode.OFF:
            # Only try to change the confirmed target temperature, when the
            # device is not off, so that we can still turn it on again later,
            # using the last confirmed target temperature.
            self._last_confirmed_target_temp = device_target_temp

        # Update confirmed state from server
        # Clear pending if it matches server state
        if (
            device_target_temp is not None and self._pending_target_temp is not None
            and abs(device_target_temp - self._pending_target_temp) < 0.5
        ):
            self._pending_target_temp = None
        if self._last_confirmed_work_mode == self._pending_work_mode:
            self._pending_work_mode = None

        # If we have no pending changes, we can update less frequently
        if (
            self._pending_target_temp is not None
            or self._pending_work_mode is not None
        ):
            # If we still have pending changes, we would like to continue polling at higher
            # frequency until the state is confirmed. This isn't a guarantee that this will
            # happen, as the coordinator has a somewhat arbitrary max retry count to avoid
            # flooding the server with requests.
            cast(
                ESIDataUpdateCoordinator, self.coordinator
            ).set_device_still_wants_refresh()

        # Update UI
        self.async_write_ha_state()
        super()._handle_coordinator_update()

    def _get_device(self) -> ESIDevice | None:
        return next(
            (
                d
                for d in self.coordinator.data.get("devices", [])
                if d.device_id == self._device_id
            ),
            None,
        )

    @property
    def available(self) -> bool:
        """Return if the entity is available."""
        return (
            super().available
            and self._get_device() is not None
            and self._last_confirmed_work_mode is not None
        )
