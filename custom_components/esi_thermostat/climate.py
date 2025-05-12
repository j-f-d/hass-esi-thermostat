"""Climate platform for ESI Thermostat."""
from __future__ import annotations

from typing import Any, Final
import logging
import requests

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    DEFAULT_NAME,
    ATTR_INSIDE_TEMPERATURE,
    ATTR_CURRENT_TEMPERATURE,
    SET_TEMP_URL,
    LOGIN_URL,
    DEVICE_LIST_URL,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_MINUTES
)
from .coordinator import ESIDataUpdateCoordinator

_LOGGER: Final = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ESI Thermostat climate platform from config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    # Wait for initial data if needed
    if not coordinator.data:
        await coordinator.async_config_entry_first_refresh()

    # Create entities for each device
    devices = coordinator.data.get("devices", [])
    entities = []
    
    for device in devices:
        try:
            entity = EsiThermostat(
                coordinator=coordinator,
                device_id=device["device_id"],
                name=device.get("device_name", DEFAULT_NAME)
            )
            entities.append(entity)
        except KeyError as err:
            _LOGGER.warning("Skipping device due to missing data: %s", err)
            continue
    
    if entities:
        async_add_entities(entities)

class EsiThermostat(CoordinatorEntity, ClimateEntity):
    """Representation of an ESI Thermostat device."""

    _attr_has_entity_name = False
    _attr_hvac_modes = [HVACMode.HEAT]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer"

    def __init__(
        self,
        coordinator: ESIDataUpdateCoordinator,
        device_id: str,
        name: str,
    ) -> None:
        """Initialize the thermostat."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}"
        self._attr_name = name
        self._attr_hvac_mode = HVACMode.HEAT
        self._pending_temperature: float | None = None
        self._is_setting = False

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=name,
            manufacturer="ESI Heating",
            model="Smart Thermostat",
        )

    @property
    def icon(self) -> str:
        """Return dynamic icon based on heating state."""
        current_temp = self.current_temperature
        target_temp = self.target_temperature
        
        if (current_temp is not None and 
            target_temp is not None and 
            current_temp < target_temp and 
            self.hvac_mode == HVACMode.HEAT):
            return "mdi:fire"
        return "mdi:thermometer"

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        if device := self._get_device():
            try:
                return float(device[ATTR_INSIDE_TEMPERATURE]) / 10
            except (KeyError, ValueError, TypeError):
                return None
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        if self._pending_temperature is not None:
            return self._pending_temperature
        if device := self._get_device():
            try:
                return float(device[ATTR_CURRENT_TEMPERATURE]) / 10
            except (KeyError, ValueError, TypeError):
                return None
        return None

    def _get_device(self) -> dict[str, Any] | None:
        """Get this device's data from coordinator."""
        devices = self.coordinator.data.get("devices", [])
        return next((d for d in devices if d["device_id"] == self._device_id), None)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        if self._is_setting:
            return

        self._is_setting = True
        self._pending_temperature = temperature
        self.async_write_ha_state()

        try:
            # Store pending update in coordinator
            if not hasattr(self.coordinator, '_pending_updates'):
                self.coordinator._pending_updates = {}
                
            self.coordinator._pending_updates[self._device_id] = int(temperature * 10)
            
            # Send update to API
            await self.hass.async_add_executor_job(
                self._set_temperature, temperature
            )
            
            # Refresh data
            await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.error("Error setting temperature: %s", err)
            self._pending_temperature = None
            self.async_write_ha_state()
            raise

        finally:
            self._is_setting = False
            self._pending_temperature = None

    def _set_temperature(self, temperature: float) -> None:
        """Send temperature setting to API."""
        if not self.coordinator.token:
            raise ValueError("No auth token")

        params = {
            "device_id": self._device_id,
            "user_id": self.coordinator.user_id,
            "current_temprature": int(temperature * 10),
            "messageId": "261a",
            "work_mode": 1,
            "token": self.coordinator.token,
        }

        response = requests.post(
            SET_TEMP_URL,
            params=params,
            timeout=10
        )

        if not response.json().get("statu"):
            raise ValueError("Temperature set failed")

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self._get_device() is not None
            and self.coordinator.token is not None
        )