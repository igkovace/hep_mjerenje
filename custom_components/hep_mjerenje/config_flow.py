
from __future__ import annotations
from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    DOMAIN, CONF_USERNAME, CONF_PASSWORD, CONF_OIB, CONF_OMM,
    CONF_DATE_COL, CONF_TIME_COL, CONF_KW_COL,
    CONF_DATE_FMT, CONF_TIME_FMT, CONF_VALUE_IS_ENERGY,
    CONF_BACKFILL_N_MONTHS, CONF_BACKFILL_DONE,
    CONF_RESET_ON_INSTALL, DEFAULT_RESET_ON_INSTALL,
    CONF_SYNC_TOTAL_TO_YTD, DEFAULT_SYNC_TOTAL_TO_YTD,
    CONF_EXPORTER_ENABLED, CONF_INFLUX_URL, CONF_INFLUX_TOKEN, CONF_INFLUX_ORG, CONF_INFLUX_BUCKET,
    CONF_EXPORT_SERIES_15M, CONF_EXPORT_SERIES_DAILY, CONF_EXPORT_SERIES_MONTHLY,
    DEFAULT_DATE_COL, DEFAULT_TIME_COL, DEFAULT_KW_COL,
    DEFAULT_DATE_FMT, DEFAULT_TIME_FMT, DEFAULT_VALUE_IS_ENERGY,
    DEFAULT_BACKFILL_N_MONTHS,
    DEFAULT_EXPORTER_ENABLED, DEFAULT_EXPORT_SERIES_15M, DEFAULT_EXPORT_SERIES_DAILY, DEFAULT_EXPORT_SERIES_MONTHLY,
)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_USERNAME): str,
    vol.Required(CONF_PASSWORD): str,
    vol.Required(CONF_OIB): str,
    vol.Required(CONF_OMM): str,
    vol.Optional(CONF_BACKFILL_N_MONTHS, default=DEFAULT_BACKFILL_N_MONTHS): int,
    vol.Optional(CONF_RESET_ON_INSTALL, default=DEFAULT_RESET_ON_INSTALL): bool,
    vol.Optional(CONF_SYNC_TOTAL_TO_YTD, default=DEFAULT_SYNC_TOTAL_TO_YTD): bool,
})

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors = {}
        if user_input is not None:
            await self.async_set_unique_id(f"{user_input[CONF_OIB]}_{user_input[CONF_OMM]}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=f"HEP {user_input[CONF_OMM]}", data=user_input, options={
                CONF_DATE_COL: DEFAULT_DATE_COL,
                CONF_TIME_COL: DEFAULT_TIME_COL,
                CONF_KW_COL: DEFAULT_KW_COL,
                CONF_DATE_FMT: DEFAULT_DATE_FMT,
                CONF_TIME_FMT: DEFAULT_TIME_FMT,
                CONF_VALUE_IS_ENERGY: DEFAULT_VALUE_IS_ENERGY,
                CONF_BACKFILL_N_MONTHS: int(user_input.get(CONF_BACKFILL_N_MONTHS, DEFAULT_BACKFILL_N_MONTHS)),
                CONF_BACKFILL_DONE: False,
                CONF_RESET_ON_INSTALL: bool(user_input.get(CONF_RESET_ON_INSTALL, DEFAULT_RESET_ON_INSTALL)),
                CONF_SYNC_TOTAL_TO_YTD: bool(user_input.get(CONF_SYNC_TOTAL_TO_YTD, DEFAULT_SYNC_TOTAL_TO_YTD)),
                CONF_EXPORTER_ENABLED: DEFAULT_EXPORTER_ENABLED,
                CONF_INFLUX_URL: "",
                CONF_INFLUX_TOKEN: "",
                CONF_INFLUX_ORG: "",
                CONF_INFLUX_BUCKET: "",
                CONF_EXPORT_SERIES_15M: DEFAULT_EXPORT_SERIES_15M,
                CONF_EXPORT_SERIES_DAILY: DEFAULT_EXPORT_SERIES_DAILY,
                CONF_EXPORT_SERIES_MONTHLY: DEFAULT_EXPORT_SERIES_MONTHLY,
            })
        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="Options", data=user_input)
        options = self._config_entry.options
        schema = vol.Schema({
            vol.Optional(CONF_DATE_COL, default=options.get(CONF_DATE_COL, DEFAULT_DATE_COL)): int,
            vol.Optional(CONF_TIME_COL, default=options.get(CONF_TIME_COL, DEFAULT_TIME_COL)): int,
            vol.Optional(CONF_KW_COL, default=options.get(CONF_KW_COL, DEFAULT_KW_COL)): int,
            vol.Optional(CONF_DATE_FMT, default=options.get(CONF_DATE_FMT, DEFAULT_DATE_FMT)): str,
            vol.Optional(CONF_TIME_FMT, default=options.get(CONF_TIME_FMT, DEFAULT_TIME_FMT)): str,
            vol.Optional(CONF_VALUE_IS_ENERGY, default=options.get(CONF_VALUE_IS_ENERGY, DEFAULT_VALUE_IS_ENERGY)): bool,
            vol.Optional(CONF_BACKFILL_N_MONTHS, default=options.get(CONF_BACKFILL_N_MONTHS, DEFAULT_BACKFILL_N_MONTHS)): int,
            vol.Optional(CONF_RESET_ON_INSTALL, default=options.get(CONF_RESET_ON_INSTALL, DEFAULT_RESET_ON_INSTALL)): bool,
            vol.Optional(CONF_SYNC_TOTAL_TO_YTD, default=options.get(CONF_SYNC_TOTAL_TO_YTD, DEFAULT_SYNC_TOTAL_TO_YTD)): bool,
            vol.Optional(CONF_EXPORTER_ENABLED, default=options.get(CONF_EXPORTER_ENABLED, DEFAULT_EXPORTER_ENABLED)): bool,
            vol.Optional(CONF_INFLUX_URL, default=options.get(CONF_INFLUX_URL, "")): str,
            vol.Optional(CONF_INFLUX_TOKEN, default=options.get(CONF_INFLUX_TOKEN, "")): str,
            vol.Optional(CONF_INFLUX_ORG, default=options.get(CONF_INFLUX_ORG, "")): str,
            vol.Optional(CONF_INFLUX_BUCKET, default=options.get(CONF_INFLUX_BUCKET, "")): str,
            vol.Optional(CONF_EXPORT_SERIES_15M, default=options.get(CONF_EXPORT_SERIES_15M, True)): bool,
            vol.Optional(CONF_EXPORT_SERIES_DAILY, default=options.get(CONF_EXPORT_SERIES_DAILY, True)): bool,
            vol.Optional(CONF_EXPORT_SERIES_MONTHLY, default=options.get(CONF_EXPORT_SERIES_MONTHLY, True)): bool,
        })
        return self.async_show_form(step_id="init", data_schema=schema)
