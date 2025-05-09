"""Constants for ESI Thermostat integration."""
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD

DOMAIN = "esi_thermostat"
PLATFORMS = ["climate"]

# API Endpoints (full URLs)
LOGIN_URL = "https://esiheating.uksouth.cloudapp.azure.com/centro/login"
DEVICE_LIST_URL = "https://esiheating.uksouth.cloudapp.azure.com/centro/getDeviceListNew"
SET_TEMP_URL = "https://esiheating.uksouth.cloudapp.azure.com/centro/setThermostatWorkModeNew"

# Configuration
DEFAULT_SCAN_INTERVAL_MINUTES = 3  # Default: 5 minutes
CONF_SCAN_INTERVAL = "scan_interval_minutes"  # Config entry key for scan interval
DEFAULT_NAME = "ESI Thermostat"