"""ESI Thermostat Water Heater Platform."""

from datetime import timedelta
from enum import IntEnum
import logging
from typing import Any, Final, cast

from esi_controls_async import ESIDevice

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

from .const import (
    DEFAULT_NAME,
    DEVICE_TYPES_WATERHEATER,
    DOMAIN,
    WATERHEATER_TH_WORK_IDLE,
)
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
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    if not coordinator.data:
        await coordinator.async_config_entry_first_refresh()

    entities: list[WaterHeaterEntity] = []
    for device in coordinator.get(set(DEVICE_TYPES_WATERHEATER), set()):
        try:
            entities.append(
                EsiWaterHeater(
                    coordinator=coordinator,
                    device_id=device.device_id,
                    name=device.device_name,
                )
            )
        except KeyError:
            continue

    if entities:
        async_add_entities(entities)


class EsiWaterHeater(CoordinatorEntity, WaterHeaterEntity):
    """ESI Water Heater Entity."""

    WORK_MODE_TO_STATE: dict[WaterHeaterWorkMode | None, str] = {
        WaterHeaterWorkMode.AUTO: STATE_ON,
        WaterHeaterWorkMode.AUTO_TEMP_OVERRIDE: STATE_ON,
        WaterHeaterWorkMode.BOOST: STATE_ON,
        WaterHeaterWorkMode.MANUAL: STATE_ON,
        WaterHeaterWorkMode.PRESET: STATE_ON,
        WaterHeaterWorkMode.OFF: STATE_OFF,
        None: STATE_OFF,
    }

    WORK_MODE_TO_OPERATION: dict[WaterHeaterWorkMode | None, str] = {
        None: STATE_OFF,
        WaterHeaterWorkMode.AUTO: OPERATION_AUTO,
        WaterHeaterWorkMode.AUTO_TEMP_OVERRIDE: OPERATION_AUTO,
        WaterHeaterWorkMode.BOOST: STATE_ON,
        WaterHeaterWorkMode.MANUAL: STATE_ON,
        WaterHeaterWorkMode.OFF: STATE_OFF,
    }

    OPERATION_TO_WORK_MODE: dict[str | None, WaterHeaterWorkMode] = {
        None: WaterHeaterWorkMode.AUTO,
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
        self._attr_target_temperature = None

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

        if self._last_confirmed_work_mode == WaterHeaterWorkMode.AUTO:
            # Setting temperature will require manual mode
            self._pending_work_mode = WaterHeaterWorkMode.AUTO_TEMP_OVERRIDE
        else:
            # Setting temperature will require manual mode
            self._pending_work_mode = WaterHeaterWorkMode.MANUAL
        self._pending_target_temp = temperature

        # Request update to server
        await self._async_perform_update()

    async def _async_perform_update(self) -> None:
        """Request a thermostat state update via the ESI server."""
        try:
            # Whichever function calls this one, it must have set
            # _pending_work_mode and may have set _pending_target_temp
            target_temp = self._pending_target_temp

            # The caller didn't set work mode, we'll ignore them
            if self._pending_work_mode is None:
                # Just request an update if no work mode is set, to
                # ensure state is up to date
                self._pending_target_temp = None
                await self.coordinator.async_request_refresh()
                return

            # The ESI API needs a temperature.
            if target_temp is None:
                # Use the last confirmed target temp if possible, since that
                # is most likely what will be desired for the next off to manual
                target_temp = self._last_confirmed_target_temp
            if target_temp is None:
                device = self._get_device()
                target_temp = device.target_temperature if device else None
            if target_temp is None:
                target_temp = DEFAULT_MANUAL_TEMPERATURE

            # Send request to server
            await cast(ESIDataUpdateCoordinator, self.coordinator).async_set_work_mode(
                self._device_id, self._pending_work_mode, target_temp
            )

            # Refresh coordinator to trigger immediate update
            await self.coordinator.async_request_refresh()

        except Exception:
            _LOGGER.exception("Update failed")

            # On failure, clear pending state
            self._pending_target_temp = None
            self._pending_work_mode = None

            # Refresh to get current server state
            await self.coordinator.async_request_refresh()

    def _handle_coordinator_update(self) -> None:
        """Update local state as reported by the coordinator."""
        device: ESIDevice | None = self._get_device()
        if device is None:
            super()._handle_coordinator_update()
            return

        try:
            # First check the work mode
            device_work_mode = device.work_mode
            if device_work_mode is not None:
                self._last_confirmed_work_mode = WaterHeaterWorkMode(device_work_mode)
        except (ValueError, TypeError, KeyError):
            _LOGGER.error(
                "Failed to parse work mode for device %s",
                self._device_id,
            )
        # Update the current operation, which needs to be one of the values specified in
        # _attr_operation_list, or None.
        self._attr_current_operation = self.WORK_MODE_TO_OPERATION.get(
            self._last_confirmed_work_mode, None
        )
        # Determine the last confirmed state based on the work mode and TH_WORK,
        # which togetherr indicate if the heater is actively heating, idle or off.
        self._last_confirmed_state = self.WORK_MODE_TO_STATE.get(
            self._last_confirmed_work_mode, STATE_ON
        )
        if self._last_confirmed_state == STATE_ON:
            if (
                device.th_work is not None
                and device.th_work == WATERHEATER_TH_WORK_IDLE
            ):
                # When TH_WORK is 0, it means the heater is at the desired temperature
                # but the work mode is still ON, so we consider it idle
                self._last_confirmed_state = STATE_IDLE

        try:
            # Update current temperature read from the device
            self._attr_current_temperature = device.measured_temperature
        except (TypeError, ValueError, KeyError):
            _LOGGER.error(
                "Failed to parse current temperature for device %s",
                self._device_id,
            )

        device_target_temp = None
        try:
            device_target_temp = device.target_temperature
        except (TypeError, ValueError, KeyError):
            _LOGGER.error(
                "Failed to parse target temperature for device %s",
                self._device_id,
            )
        if self._last_confirmed_target_temp is None:
            # If there wasn't a confirmed target temperature, use the one just read
            self._last_confirmed_target_temp = device_target_temp
        if (
            self._pending_work_mode is None
            or self._pending_work_mode == self._last_confirmed_work_mode
        ) and self._last_confirmed_work_mode is not WaterHeaterWorkMode.OFF:
            # Only try to change the confirmed target temperature, when the
            # device is not off, so that we can still turn it on again later,
            # using the last confirmed target temperature.
            self._last_confirmed_target_temp = device_target_temp

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
