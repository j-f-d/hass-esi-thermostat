"""ESI Thermostat Climate Platform."""

from __future__ import annotations

import asyncio
import contextlib
import logging

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
    ATTR_INSIDE_TEMPERATURE,
    ATTR_TARGET_TEMPERATURE,
    ATTR_WORK_MODE,
    CLIMATE_WORK_MODE_AUTO,
    CLIMATE_WORK_MODE_AUTO_TEMP_OVERRIDE,
    CLIMATE_WORK_MODE_MANUAL,
    CLIMATE_WORK_MODE_OFF,
    DEVICE_TYPES_WATERHEATER,
    DOMAIN,
    DEFAULT_NAME,
)
from .coordinator import ESIDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


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
    for device in coordinator.get([], DEVICE_TYPES_WATERHEATER):
        _LOGGER.debug(
            "Found %s with device_id: %s",
            device.get("device_name", "Unknown"),
            device["device_id"],
        )
        try:
            entities.append(
                EsiClimate(
                    coordinator=coordinator,
                    device_id=device["device_id"],
                    name=device.get("device_name", DEFAULT_NAME),
                )
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

    WORK_MODE_TO_HVAC = {
        CLIMATE_WORK_MODE_MANUAL: HVACMode.HEAT,
        CLIMATE_WORK_MODE_AUTO: HVACMode.AUTO,
        CLIMATE_WORK_MODE_AUTO_TEMP_OVERRIDE: HVACMode.AUTO,
        CLIMATE_WORK_MODE_OFF: HVACMode.OFF,
    }

    HVAC_TO_WORK_MODE = {
        HVACMode.HEAT: CLIMATE_WORK_MODE_MANUAL,
        HVACMode.AUTO: CLIMATE_WORK_MODE_AUTO,
        HVACMode.OFF: CLIMATE_WORK_MODE_OFF,
    }

    def __init__(
        self, coordinator: ESIDataUpdateCoordinator, device_id: str, name: str
    ) -> None:
        """Initialize the ESI Thermostat entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{device_id}"

        # Last known server-confirmed state
        self._last_confirmed_temp = None
        self._last_confirmed_mode = None
        self._last_confirmed_work_mode = None

        # Pending state that hasn't been confirmed by server
        self._pending_temperature = None
        self._pending_hvac_mode = None

        # Track if we're changing mode
        self._is_mode_change = False

        # Queue for serializing updates
        self._update_queue = asyncio.Queue()
        self._update_processor_task = asyncio.create_task(self._process_updates())

        # Initialize with current state
        if device := self._get_device():
            try:
                self._last_confirmed_temp = float(device[ATTR_TARGET_TEMPERATURE]) / 10
                work_mode = device.get(ATTR_WORK_MODE)
                work_mode = (
                    int(work_mode) if work_mode is not None else CLIMATE_WORK_MODE_AUTO
                )
                self._last_confirmed_work_mode = work_mode
                self._last_confirmed_mode = self.WORK_MODE_TO_HVAC.get(
                    work_mode, HVACMode.HEAT
                )
            except (TypeError, ValueError):
                pass

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=name,
            manufacturer="ESI Heating",
            model="Smart Thermostat",
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
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        # Prefer pending mode if set
        if self._pending_hvac_mode is not None:
            return self._pending_hvac_mode

        # Fallback to last confirmed mode
        if self._last_confirmed_mode is not None:
            return self._last_confirmed_mode

        # Finally try to get from device
        if device := self._get_device():
            try:
                work_mode = device.get(ATTR_WORK_MODE)
                work_mode = (
                    int(work_mode) if work_mode is not None else CLIMATE_WORK_MODE_AUTO
                )
                return self.WORK_MODE_TO_HVAC.get(work_mode, HVACMode.HEAT)
            except (TypeError, ValueError):
                return HVACMode.HEAT
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current HVAC action."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        current_temp = self.current_temperature
        target_temp = self.target_temperature

        if current_temp is None or target_temp is None:
            return HVACAction.IDLE

        if current_temp < target_temp:
            return HVACAction.HEATING
        return HVACAction.IDLE

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
        if self._pending_temperature is not None:
            return self._pending_temperature

        # Fallback to last confirmed temperature
        if self._last_confirmed_temp is not None:
            return self._last_confirmed_temp

        # Finally try to get from device
        if device := self._get_device():
            try:
                return float(device[ATTR_TARGET_TEMPERATURE]) / 10
            except (ValueError, TypeError):
                return None
        return None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        # Set pending state immediately
        self._pending_hvac_mode = hvac_mode
        self._is_mode_change = True

        # For AUTO mode, don't set a pending temperature - we'll get it from the server
        if hvac_mode == HVACMode.OFF:
            self._pending_temperature = 5.0
        else:
            self._pending_temperature = None

        # Update UI immediately
        self.async_write_ha_state()

        # Enqueue update to server
        await self._enqueue_update()

    async def async_set_temperature(self, **kwargs) -> None:
        """Set the target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        # Set pending state immediately
        self._pending_temperature = temperature
        self._is_mode_change = False

        # Handle mode transitions
        current_mode = self.hvac_mode
        if current_mode == HVACMode.OFF:
            self._pending_hvac_mode = HVACMode.HEAT
            self._is_mode_change = True
        elif current_mode == HVACMode.AUTO:
            # Keep in AUTO mode but use temp override
            self._pending_hvac_mode = HVACMode.AUTO
        else:  # Manual mode
            # Stay in manual mode
            self._pending_hvac_mode = HVACMode.HEAT

        # Update UI immediately
        self.async_write_ha_state()

        # Enqueue update to server
        await self._enqueue_update()

    async def _enqueue_update(self) -> None:
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

    async def _async_perform_update(self) -> None:
        """Perform the actual thermostat update."""
        try:
            # Capture pending state at start of update
            target_temp = self._pending_temperature
            target_mode = self._pending_hvac_mode

            # Validate we have what we need
            if target_mode is None:
                return

            # For AUTO mode without temperature, use current device temperature
            if target_mode == HVACMode.AUTO and target_temp is None:
                if device := self._get_device():
                    try:
                        target_temp = float(device[ATTR_TARGET_TEMPERATURE]) / 10
                    except (TypeError, ValueError):
                        target_temp = self._last_confirmed_temp or 20.0
                else:
                    target_temp = self._last_confirmed_temp or 20.0

            # Determine API parameters based on target mode
            if target_mode == HVACMode.AUTO:
                # Use AUTO_TEMP_OVERRIDE if we're already in AUTO and it's not a mode change
                if not self._is_mode_change and self.hvac_mode == HVACMode.AUTO:
                    work_mode = CLIMATE_WORK_MODE_AUTO_TEMP_OVERRIDE
                else:
                    work_mode = CLIMATE_WORK_MODE_AUTO
            else:
                # Use the HVAC_TO_WORK_MODE mapping for all other modes
                work_mode = self.HVAC_TO_WORK_MODE.get(
                    target_mode, CLIMATE_WORK_MODE_MANUAL
                )

            if target_temp is None:
                api_temp = None
            else:
                # Convert to API format
                api_temp = int(target_temp * 10)

            # Send request to server
            await self.coordinator.async_set_work_mode(
                self._device_id, work_mode, api_temp
            )

            # Refresh coordinator to get latest state
            await self.coordinator.async_request_refresh()

            # Special handling for AUTO mode to get schedule temperature
            if target_mode == HVACMode.AUTO:
                # Wait longer for AUTO mode to ensure scheduled temp is fetched
                await asyncio.sleep(3.0)
                await self.coordinator.async_request_refresh()

            # Clear mode change flag after processing
            self._is_mode_change = False

        except Exception:
            _LOGGER.exception("Update failed")

            # On failure, clear pending state
            self._pending_temperature = None
            self._pending_hvac_mode = None
            self._is_mode_change = False

            # Refresh to get current server state
            await self.coordinator.async_request_refresh()

    def _handle_coordinator_update(self) -> None:
        device = self._get_device()
        if not device:
            super()._handle_coordinator_update()
            return

        try:
            # Update temperature
            device_temp = float(device[ATTR_TARGET_TEMPERATURE]) / 10
            device_work_mode = device.get(ATTR_WORK_MODE)
            device_work_mode = (
                int(device_work_mode)
                if device_work_mode is not None
                else CLIMATE_WORK_MODE_AUTO
            )
            device_mode = self.WORK_MODE_TO_HVAC.get(device_work_mode, HVACMode.HEAT)

            # Update confirmed state from server
            self._last_confirmed_temp = device_temp
            self._last_confirmed_mode = device_mode
            self._last_confirmed_work_mode = device_work_mode

            # Clear pending if it matches server state
            if (
                self._pending_temperature is not None
                and abs(device_temp - self._pending_temperature) < 0.5
            ):
                self._pending_temperature = None

            if (
                self._pending_hvac_mode is not None
                and device_mode == self._pending_hvac_mode
            ):
                self._pending_hvac_mode = None

        except (TypeError, ValueError):
            pass

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
            and self._last_confirmed_work_mode is not None
        )

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity removal."""
        if self._update_processor_task:
            self._update_processor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._update_processor_task
            with contextlib.suppress(asyncio.CancelledError):
                await self._update_processor_task
