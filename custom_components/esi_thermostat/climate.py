"""ESI Thermostat Climate Platform."""

from enum import IntEnum
import logging
from typing import Final

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
    DEVICE_TYPES_WATERHEATER,  # For ignored devices (non-climate).
    DOMAIN,
    WATERHEATER_TH_WORK_IDLE,
)
from .coordinator import ESIDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# We should probably allow this to be set in the API.
DEFAULT_MANUAL_TEMPERATURE: Final = 20.0


class ClimateWorkMode(IntEnum):
    """Enumeration of climate work modes for the ESI thermostat.

    Values correspond to the device's reported work mode codes.
    """

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
    coordinator: ESIDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    if not coordinator.data:
        await coordinator.async_config_entry_first_refresh()

    entities: list[ClimateEntity] = []
    # It would be better to just get climate devices, but I don't know what the
    # device type(s) are for climate devices, so just exclude the water heater types,
    # since there is a class to handle them explicitly, but nothing else currently.
    for device in coordinator.get(set(), set(DEVICE_TYPES_WATERHEATER)):
        if device is None:
            continue
        device_id = device.device_id
        device_name = device.device_name
        if device_id is None or device_name is None:
            continue
        try:
            entities.append(
                EsiClimate(
                    coordinator=coordinator,
                    device_id=device_id,
                    name=device_name,
                )
            )
        except KeyError:
            continue

    if entities:
        async_add_entities(entities)


class EsiClimate(CoordinatorEntity[ESIDataUpdateCoordinator], ClimateEntity):
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
        self,
        coordinator: ESIDataUpdateCoordinator,
        device_id: str,
        name: str | None = DEFAULT_NAME,
    ) -> None:
        """Initialize the ESI Thermostat entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{device_id}"
        self._attr_hvac_mode = None

        # Last known server-confirmed state, all none for now, but
        # will be filled out first update.
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

        device = self.coordinator.get_device(self._device_id)

        # Whichever function calls this one, it should have set
        # _pending_work_mode and may have set _pending_target_temp and
        # there should be a device
        if device is None or self._pending_work_mode is None:
            # On failure, clear pending state
            self._pending_target_temp = None
            self._pending_work_mode = None

            # Refresh to get current server state
            await self.coordinator.async_request_refresh()
            return

        # The ESI API really needs a temperature, so make sure it isn't None.
        target_temp = (
            # First choice is the pending temperature, which may not be set if just changing modes
            self._pending_target_temp
            # First fallback is the last confirmed target temp if possible, since that
            # is most likely what will be desired for the next off->manual transition
            or self._last_confirmed_target_temp
        )
        if target_temp is None:
            # Next, use the device target temperature if it is greater than the minimum
            dt = device.target_temperature
            if dt is not None and dt > self._attr_min_temp:
                target_temp = dt
        if target_temp is None:
            # Try the current room temperature to prevent us getting colder.
            target_temp = self.current_temperature
        if (
            target_temp is None
            or target_temp < self._attr_min_temp
            or target_temp > self._attr_max_temp
        ):
            # Last resort, use the default, so that we aren't breading lysteria
            target_temp = DEFAULT_MANUAL_TEMPERATURE

        try:
            # Send request to server
            await self.coordinator.async_set_work_mode(
                device, self._pending_work_mode, target_temp
            )
        except Exception:
            _LOGGER.exception("Update failed")

            # On failure, clear pending state
            self._pending_target_temp = None
            self._pending_work_mode = None
        finally:
            # Refresh to get current server state
            await self.coordinator.async_request_refresh()

    def _handle_coordinator_update(self) -> None:
        device = self.coordinator.get_device(self._device_id)
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
        self._attr_hvac_mode = self.WORK_MODE_TO_HVAC.get(
            self._last_confirmed_work_mode, None
        )
        if self._attr_hvac_mode == HVACMode.OFF:
            self._attr_hvac_action = HVACAction.OFF
        else:
            if device.th_work == WATERHEATER_TH_WORK_IDLE:
                self._attr_hvac_action = HVACAction.IDLE
            self._attr_hvac_action = HVACAction.HEATING

        # Update current temperature
        try:
            self._attr_current_temperature = device.measured_temperature
        except (TypeError, ValueError, KeyError):
            _LOGGER.error(
                "Failed to parse current temperature for device %s",
                self._device_id,
            )

        # Until there is a confirmed target temperature, try to use the device's reported target temperature
        device_target_temp = None
        try:
            device_target_temp = device.target_temperature
            self._attr_target_temperature = device_target_temp
        except (TypeError, ValueError, KeyError):
            _LOGGER.error(
                "Failed to parse target temperature for device %s",
                self._device_id,
            )
        if self._last_confirmed_target_temp is None:
            self._last_confirmed_target_temp = device_target_temp
        if (
            (
                self._pending_work_mode is None
                or self._pending_work_mode == self._last_confirmed_work_mode
            )
            and self._last_confirmed_work_mode is not ClimateWorkMode.OFF
            and device_target_temp
            and device_target_temp > self._attr_min_temp
            and device_target_temp < self._attr_max_temp
        ):
            # Only try to change the confirmed target temperature, when the
            # device is not off, so that we can still turn it on again later,
            # using the last confirmed target temperature.
            self._last_confirmed_target_temp = device_target_temp

        # Update confirmed state from server
        # Clear pending if it matches server state
        if (
            device_target_temp is not None
            and self._pending_target_temp is not None
            and abs(device_target_temp - self._pending_target_temp) < 0.5
        ):
            self._pending_target_temp = None
        if self._last_confirmed_work_mode == self._pending_work_mode:
            self._pending_work_mode = None

        # If we have no pending changes, we can update less frequently
        if self._pending_target_temp is not None or self._pending_work_mode is not None:
            # If we still have pending changes, we would like to continue polling at higher
            # frequency until the state is confirmed. This isn't a guarantee that this will
            # happen, as the coordinator has a somewhat arbitrary max retry count to avoid
            # flooding the server with requests.
            self.coordinator.set_device_still_wants_refresh()

        # Update UI
        self.async_write_ha_state()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Return if the entity is available."""
        return (
            super().available
            and self.coordinator.get_device(self._device_id) is not None
            and self._last_confirmed_work_mode is not None
        )
