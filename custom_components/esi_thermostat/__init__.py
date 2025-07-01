"""ESI Thermostat integration for Home Assistant."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import ESIDataUpdateCoordinator

# Explicitly declare no YAML config is supported (config entry only)
CONFIG_SCHEMA = vol.Schema({}, extra=vol.ALLOW_EXTRA)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the ESI Thermostat integration from YAML (not used here)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ESI Thermostat from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Get scan interval from options
    scan_interval_minutes = entry.options.get(
        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES
    )

    # Initialize coordinator
    coordinator = ESIDataUpdateCoordinator(
        hass, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD], scan_interval_minutes
    )

    try:
        # Fetch initial data
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"Failed to initialize: {err}") from err

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator, "data": entry.data}

    # Forward setup to platforms using async forward
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Set up options update listener
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
