
from __future__ import annotations
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.helpers import aiohttp_client
from .const import DOMAIN, CONF_USERNAME, CONF_PASSWORD, CONF_OIB, CONF_OMM, SERVICE_IMPORT_HISTORY
from .api import HepMjerenjeClient
from .coordinator import HepCoordinator

PLATFORMS = [Platform.SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    session = aiohttp_client.async_get_clientsession(hass)
    data = entry.data
    client = HepMjerenjeClient(
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        oib=data[CONF_OIB],
        omm=data[CONF_OMM],
        session=session,
    )
    coordinator = HepCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["coordinator"] = coordinator

    async def handle_import_history(call):
        months = call.data.get("months", [])
        if not isinstance(months, list):
            return
        await coordinator.import_history(months)

    hass.services.async_register(DOMAIN, SERVICE_IMPORT_HISTORY, handle_import_history)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.pop(DOMAIN, None)
    return unloaded
