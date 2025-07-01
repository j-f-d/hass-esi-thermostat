"""Constants for ESI Thermostat integration."""

from typing import Final

from homeassistant.const import Platform

# Domain
DOMAIN: Final = "esi_thermostat"

# Platforms
# PLATFORMS: Final[list[Platform]] = [Platform.CLIMATE, Platform.WATER_HEATER]
PLATFORMS: Final[list[Platform]] = [Platform.CLIMATE]

# API Endpoints
LOGIN_URL: Final = "https://esiheating.uksouth.cloudapp.azure.com/centro/login"
DEVICE_LIST_URL: Final = (
    "https://esiheating.uksouth.cloudapp.azure.com/centro/getDeviceListNew"
)
SET_TEMP_URL: Final = (
    "https://esiheating.uksouth.cloudapp.azure.com/centro/setThermostatWorkModeNew"
)

# Configuration
DEFAULT_SCAN_INTERVAL_MINUTES: Final = 3
CONF_SCAN_INTERVAL: Final = "scan_interval_minutes"
DEFAULT_NAME: Final = "ESI Thermostat"

# Device Attributes
ATTR_INSIDE_TEMPERATURE: Final = "inside_temparature"
ATTR_CURRENT_TEMPERATURE: Final = "current_temprature"
ATTR_WORK_MODE: Final = "work_mode"

# Work modes
WORK_MODE_MANUAL: Final = 5
WORK_MODE_AUTO: Final = 0
WORK_MODE_AUTO_TEMP_OVERRIDE: Final = 1  # ADD THIS LINE
WORK_MODE_OFF: Final = 4
