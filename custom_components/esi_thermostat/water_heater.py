"""ESI Thermostat Water Heater Platform."""

from datetime import timedelta
from enum import IntEnum
import logging
from typing import Any, Final

from homeassistant.components.water_heater import (
    STATE_OFF,
    STATE_ON,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DEVICE_TYPES_WATERHEATER, DOMAIN
from .coordinator import ESIDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

STATE_IDLE: Final = "idle"
OPERATION_AUTO: Final = "auto"
OPERATION_AUTO_OVERRIDE: Final = "auto (+temp)"
OPERATION_BOOST: Final = "boost"

# We should probably allow this to be set in the API.
DEFAULT_MANUAL_TEMPERATURE: Final = 55.0


class WaterHeaterWorkMode(IntEnum):
    """Work mode for Water Heater devices."""

    # The temperature is set based on a schedule, learned behavior, AI or some
    # other related mechanism. User is not able to adjust the temperature
    AUTO = 0
    # All activity disabled / Device is off/standby
    OFF = 1
    # Heating
    MANUAL = 2
    PRESET = 3
    AUTO_TEMP_OVERRIDE = 4
    BOOST = 5


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize water heater platform."""
    coordinator: ESIDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    if not coordinator.data:
        await coordinator.async_config_entry_first_refresh()

    entities: list[WaterHeaterEntity] = []
    for device in coordinator.get(set(DEVICE_TYPES_WATERHEATER), set()):
        if device is None:
            continue
        device_id = device.device_id
        device_name = device.device_name
        if device_id is None or device_name is None:
            continue
        try:
            entities.append(
                EsiWaterHeater(
                    coordinator=coordinator,
                    device_id=device_id,
                    name=device_name,
                )
            )
        except KeyError:
            continue

    if entities:
        async_add_entities(entities)


class EsiWaterHeater(CoordinatorEntity[ESIDataUpdateCoordinator], WaterHeaterEntity):
    """ESI Water Heater Entity."""

    WORK_MODE_TO_STATE: dict[WaterHeaterWorkMode, str] = {
        WaterHeaterWorkMode.AUTO: STATE_ON,
        WaterHeaterWorkMode.OFF: STATE_OFF,
        WaterHeaterWorkMode.MANUAL: STATE_ON,
        WaterHeaterWorkMode.PRESET: STATE_ON,
        WaterHeaterWorkMode.AUTO_TEMP_OVERRIDE: STATE_ON,
        WaterHeaterWorkMode.BOOST: STATE_ON,
    }

    WORK_MODE_TO_OPERATION: dict[WaterHeaterWorkMode, str] = {
        WaterHeaterWorkMode.AUTO: OPERATION_AUTO,
        WaterHeaterWorkMode.OFF: STATE_OFF,
        WaterHeaterWorkMode.MANUAL: STATE_ON,
        WaterHeaterWorkMode.PRESET: STATE_ON,
        WaterHeaterWorkMode.AUTO_TEMP_OVERRIDE: OPERATION_AUTO,
        WaterHeaterWorkMode.BOOST: STATE_ON,
    }

    OPERATION_TO_WORK_MODE: dict[str, WaterHeaterWorkMode] = {
        OPERATION_AUTO: WaterHeaterWorkMode.AUTO,
        OPERATION_AUTO_OVERRIDE: WaterHeaterWorkMode.AUTO_TEMP_OVERRIDE,
        OPERATION_BOOST: WaterHeaterWorkMode.BOOST,
        STATE_OFF: WaterHeaterWorkMode.OFF,
        STATE_ON: WaterHeaterWorkMode.MANUAL,
    }

    _attr_has_entity_name = False
    _attr_supported_features = (
        #        WaterHeaterEntityFeature.AWAY_MODE |
        WaterHeaterEntityFeature.ON_OFF
        | WaterHeaterEntityFeature.OPERATION_MODE
        | WaterHeaterEntityFeature.TARGET_TEMPERATURE
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_operation_list = [
        STATE_OFF,
        OPERATION_AUTO,
        STATE_ON,
    ]
    _attr_min_temp = 25.0
    _attr_max_temp = 65.0
    _attr_target_temperature_step = 0.5
    _attr_precision = 0.5

    def __init__(
        self,
        coordinator: ESIDataUpdateCoordinator,
        device_id: str,
        name: str | None = DEFAULT_NAME,
    ) -> None:
        """Initialize the ESI Water Heater Entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{device_id}"
        self._attr_current_operation = None
        self._attr_current_temperature = None

        # Last known server-confirmed state, all none for now, but
        # will be filled out first update.
        self._last_confirmed_target_temp: float | None = None
        self._last_confirmed_state: str | None = None
        self._last_confirmed_work_mode: WaterHeaterWorkMode | None = None

        # Pending state that hasn't been confirmed by server
        self._pending_target_temp: float | None = None
        self._pending_work_mode: WaterHeaterWorkMode | None = None

        # Set short update to get initial state
        self.coordinator.update_interval = timedelta(seconds=1)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=name,
            manufacturer="ESI Heating",
            model="Water Heater Thermostat",
        )

    async def async_set_water_heater_mode(self, work_mode: WaterHeaterWorkMode) -> None:
        """Set the HVAC mode."""
        if work_mode == WaterHeaterWorkMode.OFF:
            self._pending_target_temp = self._attr_min_temp
        # Set pending state immediately
        self._pending_work_mode = work_mode

        # Request update to server
        await self._async_perform_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the water heater on."""
        await self.async_set_water_heater_mode(WaterHeaterWorkMode.MANUAL)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the water heater off."""
        await self.async_set_water_heater_mode(WaterHeaterWorkMode.OFF)

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set new target operation mode."""
        await self.async_set_water_heater_mode(
            self.OPERATION_TO_WORK_MODE.get(operation_mode, WaterHeaterWorkMode.AUTO)
        )

    async def async_set_temperature(self, **kwargs) -> None:
        """Set the target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        # Overriding temperature implies manual mode
        self._pending_work_mode = WaterHeaterWorkMode.MANUAL
        self._pending_target_temp = temperature

        # Request update to server
        await self._async_perform_update()

    async def _async_perform_update(self) -> None:
        """Request a thermostat state update via the ESI server."""

        device = self.coordinator.get_device(self._device_id)

        # Whichever function calls this one, it should have set
        # _pending_work_mode and may have set _pending_target_temp and
        # there should be a device
        if device is None or self._pending_work_mode is None:
            # On failure, clear pending state
            self._pending_work_mode = None
            self._pending_target_temp = None

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
        if (
            target_temp is None
            or target_temp < self._attr_min_temp
            or target_temp > self._attr_max_temp
        ):
            # Last resort, use the default, so that we aren't breeding lysteria
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
        """Update local state as reported by the coordinator."""

        state = self.coordinator.get_device_state(
            self.coordinator.get_device(self._device_id)
        )
        if state is None:
            self.async_write_ha_state()
            return

        try:
            self._last_confirmed_work_mode = WaterHeaterWorkMode(state.work_mode)
        except (ValueError, AttributeError, TypeError):
            _LOGGER.error(
                "Invalid work mode (%d) for device %s",
                state.work_mode,
                self._device_id
            )
            self.async_write_ha_state()
            return

        # Update the current operation, which needs to be one of the values specified in
        # _attr_operation_list, or None.
        self._attr_current_operation = self.WORK_MODE_TO_OPERATION.get(self._last_confirmed_work_mode)

        # Determine the last confirmed state based on the work mode and TH_WORK,
        # which togetherr indicate if the heater is actively heating, idle or off.
        self._last_confirmed_state = self.WORK_MODE_TO_STATE.get(self._last_confirmed_work_mode)
        if self._last_confirmed_state == STATE_ON:
            if state.idle:
                # The idle state indicates the measured temperature is close to the
                # target temperature that no heating is required, but the confirmed
                # state is ON, so change that to IDLE.
                self._last_confirmed_state = STATE_IDLE

        # Update displayed current temperature
        self._attr_current_temperature = state.measured_temp

        if self._last_confirmed_state == STATE_OFF:
            # When off, don't report a target temperature
            self._attr_target_temperature = None
        else:
            self._attr_target_temperature = state.target_temp

        # When the device's target temperature is reasonable, use it as last confirmed.
        if (
            self._last_confirmed_work_mode is not WaterHeaterWorkMode.OFF
            and state.target_temp > self._attr_min_temp
            and state.target_temp <= self._attr_max_temp
        ):
            # Only try to change the confirmed target temperature, when the
            # device is not off, so that we can still turn it on again later,
            # using the last confirmed target temperature. Avoid setting
            # the confirmed target temp to min, since that is reported when
            # the device is in auto mode, but not in an 'on' part of the schedule.
            self._last_confirmed_target_temp = state.target_temp

        # Clear pending if they match the server state
        if (
            self._pending_target_temp is not None
            and abs(state.target_temp - self._pending_target_temp) < 0.5
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

    @property
    def available(self) -> bool:
        """Indicate whether the entity is available."""
        return (
            self.coordinator.available()
            # Need to check that the last update included a report for this device
            and self.coordinator.get_device(self._device_id) is not None
            # If there isn't a confirmed work mode, the device data isn't as expected.
            and self._last_confirmed_work_mode is not None
        )
