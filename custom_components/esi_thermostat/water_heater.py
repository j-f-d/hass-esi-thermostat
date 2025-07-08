"""ESI Thermostat Water Heater Platform."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import timedelta
from typing import Any, Final

from homeassistant.components.water_heater import (
    STATE_OFF,
    STATE_ON,
    WaterHeaterEntity,
    WaterHeaterEntityDescription,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_DEVICE_ID,
    ATTR_DEVICE_NAME,
    ATTR_INSIDE_TEMPERATURE,
    ATTR_TARGET_TEMPERATURE,
    ATTR_TH_WORK,
    ATTR_WORK_MODE,
    DEFAULT_NAME,
    DEVICE_TYPES_WATERHEATER,
    DOMAIN,
    WATERHEATER_WORK_MODE_AUTO,
    WATERHEATER_WORK_MODE_AUTO_TEMP_OVERRIDE,
    WATERHEATER_WORK_MODE_BOOST,
    WATERHEATER_WORK_MODE_MANUAL,
    WATERHEATER_WORK_MODE_OFF,
)
from .coordinator import ESIDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

STATE_IDLE: Final = "idle"
OPERATION_AUTO: Final = "auto"
OPERATION_AUTO_OVERRIDE: Final = "auto (+temp)"
OPERATION_BOOST: Final = "boost"


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
    for device in coordinator.get(DEVICE_TYPES_WATERHEATER, []):
        try:
            entities.append(
                EsiWaterHeater(
                    coordinator=coordinator,
                    device_id=device[ATTR_DEVICE_ID],
                    name=device.get(ATTR_DEVICE_NAME, DEFAULT_NAME),
                )
            )
        except KeyError:
            continue

    if entities:
        async_add_entities(entities)


class EsiWaterHeater(CoordinatorEntity, WaterHeaterEntity):
    """ESI Water Heater Entity."""

    WORK_MODE_TO_STATE = {
        WATERHEATER_WORK_MODE_AUTO: STATE_ON,
        WATERHEATER_WORK_MODE_AUTO_TEMP_OVERRIDE: STATE_ON,
        WATERHEATER_WORK_MODE_BOOST: STATE_ON,
        WATERHEATER_WORK_MODE_MANUAL: STATE_ON,
        WATERHEATER_WORK_MODE_OFF: STATE_OFF,
        None: STATE_OFF,
    }

    WORK_MODE_TO_OPERATION = {
        None: STATE_OFF,
        WATERHEATER_WORK_MODE_AUTO: OPERATION_AUTO,
        WATERHEATER_WORK_MODE_AUTO_TEMP_OVERRIDE: OPERATION_AUTO,
        WATERHEATER_WORK_MODE_BOOST: STATE_ON,
        WATERHEATER_WORK_MODE_MANUAL: STATE_ON,
        WATERHEATER_WORK_MODE_OFF: STATE_OFF,
    }

    OPERATION_TO_WORK_MODE = {
        None: WATERHEATER_WORK_MODE_AUTO,
        OPERATION_AUTO: WATERHEATER_WORK_MODE_AUTO,
        OPERATION_AUTO_OVERRIDE: WATERHEATER_WORK_MODE_AUTO_TEMP_OVERRIDE,
        OPERATION_BOOST: WATERHEATER_WORK_MODE_BOOST,
        STATE_OFF: WATERHEATER_WORK_MODE_OFF,
        STATE_ON: WATERHEATER_WORK_MODE_MANUAL,
    }

    entity_description = WaterHeaterEntityDescription(
        key="esi_water_heater",
        name="ESI Water Heater",
        icon="mdi:water-boiler",
    )
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
        self, coordinator: ESIDataUpdateCoordinator, device_id: str, name: str
    ) -> None:
        """Initialize the ESI Water Heater Entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{device_id}"

        # Last known server-confirmed state
        self._last_confirmed_target_temp: float | None = None
        self._last_confirmed_state: str | None = None
        self._last_confirmed_work_mode: int | None = None

        # Pending state that hasn't been confirmed by server
        self._pending_target_temperature: float | None = None
        self._pending_work_mode: int | None = None

        # Track if we're changing state
        self._is_state_change = False

        # Queue for serializing updates
        self._update_queue = asyncio.Queue()
        self._update_processor_task = asyncio.create_task(self._process_updates())
        self._initial_update_interval = coordinator.update_interval

        # Initialize with current state
        if device := self._get_device():
            try:
                self._last_confirmed_target_temp = (
                    float(device[ATTR_TARGET_TEMPERATURE]) / 10
                )
            except (ValueError, TypeError):
                self._last_confirmed_target_temp = None

            work_mode = device.get(ATTR_WORK_MODE)
            if work_mode is not None:
                try:
                    self._last_confirmed_work_mode = int(work_mode)
                except (ValueError, TypeError):
                    self._last_confirmed_work_mode = None

        # Try to set the workmode, or indicate that it is unknown if we couldn't
        # get the device state
        self._attr_current_operation = self.WORK_MODE_TO_OPERATION.get(
            self._last_confirmed_work_mode, STATE_OFF
        )

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=name,
            manufacturer="ESI Heating",
            model="Water Heater Thermostat",
        )

    async def _process_updates(self) -> None:
        """Process update requests sequentially from the queue."""
        while True:
            try:
                # Get next update request from queue (waits if empty)
                await self._update_queue.get()

                # Process the update
                await self._async_perform_update()

            except asyncio.CancelledError:
                # Task cancelled, exit cleanly
                return
            except Exception:
                _LOGGER.exception("Error processing update")
            finally:
                self._update_queue.task_done()

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        if device := self._get_device():
            try:
                return float(device[ATTR_INSIDE_TEMPERATURE]) / 10
            except (ValueError, TypeError):
                return None
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        # Prefer pending temperature if set
        if self._pending_target_temperature is not None:
            return self._pending_target_temperature

        # Fallback to last confirmed temperature
        if self._last_confirmed_target_temp is not None:
            return self._last_confirmed_target_temp

        # Finally try to get from device
        if device := self._get_device():
            try:
                self._last_confirmed_target_temp = (
                    float(device[ATTR_TARGET_TEMPERATURE]) / 10
                )
            except (ValueError, TypeError):
                return None
            else:
                return self._last_confirmed_target_temp
        return None

    async def async_set_water_heater_mode(self, work_mode: int) -> None:
        """Set the HVAC mode."""
        # Set pending state immediately
        self._pending_work_mode = work_mode
        self._is_state_change = True

        # Update the current operation based on the pending work mode,
        # so that the UI reflects the intended change
        self._attr_current_operation = self.WORK_MODE_TO_OPERATION.get(
            self._pending_work_mode, STATE_OFF
        )

        # Update UI immediately
        self.async_write_ha_state()

        # Enqueue update to server
        await self._async_enqueue_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the water heater on."""
        await self.async_set_water_heater_mode(WATERHEATER_WORK_MODE_MANUAL)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the water heater on."""
        await self.async_set_water_heater_mode(WATERHEATER_WORK_MODE_OFF)

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set new target operation mode."""
        await self.async_set_water_heater_mode(
            self.OPERATION_TO_WORK_MODE.get(operation_mode, WATERHEATER_WORK_MODE_AUTO)
        )

    async def async_set_temperature(self, **kwargs) -> None:
        """Set the target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        # Unify the code whether or not we're acutally changing state
        if self._pending_work_mode is None:
            self._pending_work_mode = self._last_confirmed_work_mode

        if self._pending_work_mode != WATERHEATER_WORK_MODE_MANUAL:
            # Setting temperature from another state (such as off), so go to manual mode
            self._pending_work_mode = WATERHEATER_WORK_MODE_MANUAL
            self._pending_target_temperature = temperature
            self._is_state_change = True
        else:
            # Already in manual mode, just set the temperature
            self._pending_target_temperature = temperature

        # Update the current operation based on the pending work mode,
        # so that the UI reflects the intended change
        self._attr_current_operation = self.WORK_MODE_TO_OPERATION.get(
            self._pending_work_mode, STATE_OFF
        )

        # Update UI immediately
        self.async_write_ha_state()

        # Enqueue update to server
        await self._async_enqueue_update()

    def _enqueue_update(self) -> None:
        """Add update request to the queue."""
        try:
            # Clear any existing pending updates to ensure only latest is processed
            while not self._update_queue.empty():
                self._update_queue.get_nowait()
                self._update_queue.task_done()

            # Put latest update request in queue
            self._update_queue.put_nowait("update")
        except asyncio.QueueEmpty:
            # Queue was already empty, just add new request
            self._update_queue.put_nowait("update")
        except Exception:
            _LOGGER.exception("Failed to enqueue update")

    async def _async_enqueue_update(self) -> None:
        """Enqueue an update request to be processed."""
        await self._update_queue.put("update")

    async def _async_perform_update(self) -> None:
        """Perform the actual thermostat update."""
        try:
            # Capture pending state at start of update
            target_temp = self._pending_target_temperature
            target_work_mode = self._pending_work_mode

            # Validate we have what we need
            if target_work_mode is None:
                return

            if target_work_mode == WATERHEATER_WORK_MODE_OFF:
                # If we're currently off, we can't set the temperature and we
                # expect the thermostat to be at min temperature, when we
                # get the status.
                target_temp = None
                self._pending_target_temperature = None
                self._last_confirmed_target_temp = None
            elif target_work_mode == WATERHEATER_WORK_MODE_AUTO:
                # If we're in AUTO mode, we can't change the target temperature,
                # so we use the last confirmed target temperature.
                target_temp = self._last_confirmed_target_temp
                # Reset stored temperatures, so that we force the temperature
                # to be read from the device on the next update
                self._pending_target_temperature = None
                self._last_confirmed_target_temp = None

            if target_temp is None:
                target_temp = self._attr_min_temp

                # Convert to API format
            api_temp = int(target_temp * 10)

            # Send request to server
            await self.coordinator.async_set_work_mode(
                self._device_id, target_work_mode, api_temp
            )

            # Increase the refresh interval to poll regularly until the state is confirmed
            self.coordinator.update_interval = timedelta(seconds=2)
            # Refresh coordinator to trigger immediate update
            await self.coordinator.async_request_refresh()

            # Clear mode change flag after processing
            self._is_state_change = False

        except Exception:
            _LOGGER.exception("Update failed")

            # On failure, clear pending state
            self._pending_target_temperature = None
            self._pending_work_mode = None
            self._is_state_change = False

            # Refresh to get current server state
            await self.coordinator.async_request_refresh()

    def _handle_coordinator_update(self) -> None:
        device = self._get_device()
        if not device:
            super()._handle_coordinator_update()
            return
        try:
            # Update temperature
            self._last_confirmed_target_temp = (
                float(device[ATTR_TARGET_TEMPERATURE]) / 10
            )
        except (TypeError, ValueError):
            _LOGGER.error(
                "Failed to parse target temperature for device %s: %s",
                self._device_id,
                device.get(ATTR_TARGET_TEMPERATURE),
            )
            self._last_confirmed_target_temp = None

        work_mode = device.get(ATTR_WORK_MODE)
        if work_mode is not None:
            try:
                self._last_confirmed_work_mode = int(work_mode)
            except (ValueError, TypeError):
                self._last_confirmed_work_mode = None

        # Try to set the workmode, or indicate that it is unknown if we couldn't
        # get the device state
        self._attr_current_operation = self.WORK_MODE_TO_OPERATION.get(
            self._last_confirmed_work_mode, f"unknown({self._last_confirmed_work_mode})"
        )

        self._last_confirmed_state = self.WORK_MODE_TO_STATE.get(
            self._last_confirmed_work_mode, STATE_ON
        )
        if self._last_confirmed_state == STATE_ON and device.get(ATTR_TH_WORK) == "0":
            # When TH_WORK is 0, it means the heater at the desired temperature
            # but the work mode is still ON, so we consider it idle
            self._last_confirmed_state = STATE_IDLE

        # Clear pending if it matches server state
        if (
            self._pending_target_temperature is not None
            and self._last_confirmed_target_temp == self._pending_target_temperature
        ):
            self._pending_target_temperature = None

        if (
            self._pending_work_mode is not None
            and self._last_confirmed_work_mode == self._pending_work_mode
        ):
            self._pending_work_mode = None

        # If we have no pending changes, we can update less frequently
        if self._pending_target_temperature is None and self._pending_work_mode is None:
            # Reset the update interval if it has been changed
            if self.coordinator.update_interval != self._initial_update_interval:
                self.coordinator.update_interval = self._initial_update_interval
        else:
            # Enqueue update to server
            self._enqueue_update()

        # Update UI
        self.async_write_ha_state()
        super()._handle_coordinator_update()

    def _get_device(self) -> dict | None:
        return next(
            (
                d
                for d in self.coordinator.data.get("devices", [])
                if d["device_id"] == self._device_id
            ),
            None,
        )

    @property
    def available(self) -> bool:
        """Return if the entity is available."""
        return (
            super().available
            and self._get_device() is not None
            and self.coordinator.token is not None
        )

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity removal."""
        if self._update_processor_task:
            self._update_processor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._update_processor_task
            with contextlib.suppress(asyncio.CancelledError):
                await self._update_processor_task
