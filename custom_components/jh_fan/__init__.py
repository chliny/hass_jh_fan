"""The JH Voice Fan integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import JHFanCoordinator

PLATFORMS: list[Platform] = [Platform.FAN, Platform.SWITCH, Platform.SELECT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    address = entry.data[CONF_ADDRESS]

    # Create and store the coordinator
    coordinator = JHFanCoordinator(hass, address)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
