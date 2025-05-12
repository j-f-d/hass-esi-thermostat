"""Constants for ESI Thermostat integration."""
from typing import Final
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform

# Domain
DOMAIN: Final = "esi_thermostat"

# Platforms
PLATFORMS: Final[list[Platform]] = [Platform.CLIMATE]

# API Endpoints
LOGIN_URL: Final = "https://esiheating.uksouth.cloudapp.azure.com/centro/login"
DEVICE_LIST_URL: Final = "https://esiheating.uksouth.cloudapp.azure.com/centro/getDeviceListNew"
SET_TEMP_URL: Final = "https://esiheating.uksouth.cloudapp.azure.com/centro/setThermostatWorkModeNew"

# Configuration
DEFAULT_SCAN_INTERVAL_MINUTES: Final = 3
CONF_SCAN_INTERVAL: Final = "scan_interval_minutes"
DEFAULT_NAME: Final = "ESI Thermostat"

# Additional constants
ATTR_INSIDE_TEMPERATURE: Final = "inside_temparature"  # Note: Typo matches API response
ATTR_CURRENT_TEMPERATURE: Final = "current_temprature"  # Note: Typo matches API response