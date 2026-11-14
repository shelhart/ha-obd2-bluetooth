"""OBD-II Bluetooth (ELM327) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .bluez import BluezClient, BluezError
from .coordinator import ObdCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

type ObdConfigEntry = ConfigEntry[ObdCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ObdConfigEntry) -> bool:
    bluez = BluezClient()
    try:
        await bluez.start()
    except BluezError as err:
        await bluez.stop()
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = ObdCoordinator(hass, entry, bluez)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ObdConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_close()
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: ObdConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
