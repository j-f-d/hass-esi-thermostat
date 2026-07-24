"""Constants for ESI Thermostat integration."""

from typing import Final

from homeassistant.const import Platform

# Domain
DOMAIN: Final = "esi_thermostat"

# Platforms
PLATFORMS: Final[list[Platform]] = [Platform.CLIMATE, Platform.WATER_HEATER]

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

# TH_WORK
WATERHEATER_TH_WORK_IDLE: Final = "0"
WATERHEATER_TH_WORK_HEATING: Final = "1"
