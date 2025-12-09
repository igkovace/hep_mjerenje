
from __future__ import annotations
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.device_registry import async_get as async_get_device_registry

from .const import (
    DOMAIN, CONF_USERNAME, CONF_PASSWORD, CONF_OIB, CONF_OMM, SERVICE_IMPORT_HISTORY,
    CONF_BACKFILL_N_MONTHS, CONF_BACKFILL_DONE,
    CONF_RESET_ON_INSTALL,
)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    from .api import HepMjerenjeClient
    from .coordinator import HepCoordinator

    session = aiohttp_client.async_get_clientsession(hass)
    data = entry.data

    client = HepMjerenjeClient(
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        oib=data[CONF_OIB],
        omm=data[CONF_OMM],
        session=session,
    )

    store_key = entry.unique_id or f"{data[CONF_OIB]}_{data[CONF_OMM]}"
    coordinator = HepCoordinator(hass, client, data[CONF_OMM], store_key=store_key)
    coordinator.set_options(entry.options)

    # Reset/backfill BEFORE first refresh
    opts = dict(entry.options)
    if bool(opts.get(CONF_RESET_ON_INSTALL, True)) and not opts.get(CONF_BACKFILL_DONE, False):
        try:
            await coordinator.reset_persist()
        except Exception:
            pass

    if not opts.get(CONF_BACKFILL_DONE, False):
        n = int(opts.get(CONF_BACKFILL_N_MONTHS, 12))
        months = []
        dt = datetime.now().replace(day=1) - timedelta(days=1)
        for _ in range(n):
            months.append(dt.strftime("%m.%Y"))
            dt = (dt.replace(day=1) - timedelta(days=1))
        try:
            await coordinator.import_history(list(reversed(months)))
            opts[CONF_BACKFILL_DONE] = True
            hass.config_entries.async_update_entry(entry, options=opts)
        except Exception:
            pass

    await coordinator.async_config_entry_first_refresh()

    # Device hierarchy
    dev_reg = async_get_device_registry(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "hep_account")},
        name="HEP ODS Account",
        manufacturer="HEP ODS",
        model="Mjerenje Portal",
    )
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, data[CONF_OMM])},
        name=f"HEP {data[CONF_OMM]}",
        manufacturer="HEP ODS",
        model="Smart Meter",
        via_device=(DOMAIN, "hep_account"),
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["coordinator"] = coordinator

    async def handle_import_history(call):
        months = call.data.get("months", [])
        force = bool(call.data.get("force", False))
        if not isinstance(months, list):
            return
        await coordinator.import_history(months, force=force)
        await coordinator.async_request_refresh()

    async def handle_import_years(call):
        years = call.data.get("years", [])
        force = bool(call.data.get("force", False))
        if not isinstance(years, list):
            return
        await coordinator.import_years(years, force=force)
        await coordinator.async_request_refresh()

    async def handle_reset_totals(call):
        await coordinator.reset_persist()
        await coordinator.async_request_refresh()

    async def handle_clear_import_cache(call):
        await coordinator.clear_import_cache()
        await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_IMPORT_HISTORY, handle_import_history)
    hass.services.async_register(DOMAIN, "import_years", handle_import_years)
    hass.services.async_register(DOMAIN, "reset_totals", handle_reset_totals)
    hass.services.async_register(DOMAIN, "clear_import_cache", handle_clear_import_cache)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.pop(DOMAIN, None)
    return unloaded
