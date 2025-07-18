"""Constants for ESI Thermostat integration."""

from typing import Final

from homeassistant.const import Platform

# Domain
DOMAIN: Final = "esi_thermostat"

# Platforms
PLATFORMS: Final[list[Platform]] = [Platform.CLIMATE, Platform.WATER_HEATER]

# API Endpoints
ESICENTRO_URL: Final = "https://esiheating.uksouth.cloudapp.azure.com/centro"
LOGIN_URL: Final = ESICENTRO_URL + "/login"
DEVICE_LIST_URL: Final = ESICENTRO_URL + "/getDeviceListNew"
SET_TEMP_URL: Final = ESICENTRO_URL + "/setThermostatWorkModeNew"

# Configuration
DEFAULT_NAME: Final = "ESI Thermostat"
# Since the API requires us to poll the server, we limit the
# frequency to avoid flooding the server.
CONF_SCAN_INTERVAL: Final = "scan_interval_minutes"
DEFAULT_SCAN_INTERVAL_MINUTES: Final = 3
# After a status change, we poll the server more frequently
# until the state is confirmed or the MAX_HIGH_FREQUENCY_POLL_COUNT
# is exceeded.
MAX_HIGH_FREQUENCY_POLL_COUNT: Final = 10

# Device Types
DEVICE_TYPES_CLIMATE: Final = ["80"]  # Unverified
DEVICE_TYPES_WATERHEATER: Final = ["81"]

# Device Attributes
ATTR_DEVICE_ID: Final = "device_id"
ATTR_DEVICE_NAME: Final = "device_name"
ATTR_DEVICE_TYPE: Final = "device_type"
# To avoid confusion don't use ATTR_CURRENT_TEMPERATURE
# inside_temperature is what HASS normally calls current_temperature.
ATTR_INSIDE_TEMPERATURE: Final = "inside_temparature"
# cuurent_temperature is what HASS normally calls target_temperature.
ATTR_TARGET_TEMPERATURE: Final = "current_temprature"
ATTR_WORK_MODE: Final = "work_mode"
ATTR_TH_WORK: Final = "th_work"

# Work modes
CLIMATE_WORK_MODE_AUTO: Final = 0
CLIMATE_WORK_MODE_AUTO_TEMP_OVERRIDE: Final = 1
CLIMATE_WORK_MODE_OFF: Final = 4
CLIMATE_WORK_MODE_MANUAL: Final = 5
WATERHEATER_WORK_MODE_AUTO: Final = 0
WATERHEATER_WORK_MODE_OFF: Final = 1
WATERHEATER_WORK_MODE_MANUAL: Final = 2
WATERHEATER_WORK_MODE_AUTO_TEMP_OVERRIDE: Final = 4
WATERHEATER_WORK_MODE_BOOST: Final = 5

WATERHEATER_TH_WORK_IDLE: Final = 0
WATERHEATER_TH_WORK_HEATING: Final = 1
