
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Dict, List
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.dt import now
from .const import (
    KEY_CONS_TOTAL, KEY_EXP_TOTAL,
    KEY_CONS_MONTH, KEY_EXP_MONTH,
    KEY_CONS_TODAY, KEY_EXP_TODAY,
    DEFAULT_SCAN_INTERVAL_MINUTES,
)
from .api import HepMjerenjeClient

_LOGGER = logging.getLogger(__name__)

class HepCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, client: HepMjerenjeClient):
        super().__init__(
            hass,
            _LOGGER,
            name="HEP Mjerenje",
            update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES),
        )
        self._client = client
        self._current_month_str = now().strftime("%m.%Y")
        self._cache: Dict[str, Dict] = {}

    async def _async_update_data(self) -> Dict:
        await self._client.login()
        p_rows, r_rows = await self._client.get_month(self._current_month_str)
        cons_month_kwh = sum([row['kw']/4.0 for row in p_rows])
        exp_month_kwh = sum([row['kw']/4.0 for row in r_rows])
        today = now().date()
        cons_today_kwh = sum([row['kw']/4.0 for row in p_rows if row['ts'].date() == today])
        exp_today_kwh = sum([row['kw']/4.0 for row in r_rows if row['ts'].date() == today])
        prev_cons_total = float(self._cache.get(KEY_CONS_TOTAL, {}).get('value', 0.0))
        prev_exp_total = float(self._cache.get(KEY_EXP_TOTAL, {}).get('value', 0.0))
        data = {
            KEY_CONS_TOTAL: prev_cons_total if prev_cons_total > 0 else cons_month_kwh,
            KEY_EXP_TOTAL:  prev_exp_total  if prev_exp_total  > 0 else exp_month_kwh,
            KEY_CONS_MONTH: cons_month_kwh,
            KEY_EXP_MONTH:  exp_month_kwh,
            KEY_CONS_TODAY: cons_today_kwh,
            KEY_EXP_TODAY:  exp_today_kwh,
            "last_update": datetime.utcnow().isoformat(),
        }
        self._cache[KEY_CONS_TOTAL] = {"value": data[KEY_CONS_TOTAL]}
        self._cache[KEY_EXP_TOTAL]  = {"value": data[KEY_EXP_TOTAL]}
        return data

    async def import_history(self, month_list: List[str]) -> Dict:
        await self._client.login()
        cons_total = 0.0
        exp_total = 0.0
        for m in month_list:
            p_rows, r_rows = await self._client.get_month(m)
            cons_total += sum([row['kw']/4.0 for row in p_rows])
            exp_total  += sum([row['kw']/4.0 for row in r_rows])
        self._cache[KEY_CONS_TOTAL] = {"value": cons_total}
        self._cache[KEY_EXP_TOTAL]  = {"value": exp_total}
        self.async_set_updated_data({
            KEY_CONS_TOTAL: cons_total,
            KEY_EXP_TOTAL: exp_total,
            KEY_CONS_MONTH: 0.0,
            KEY_EXP_MONTH: 0.0,
            KEY_CONS_TODAY: 0.0,
            KEY_EXP_TODAY: 0.0,
            "last_update": datetime.utcnow().isoformat(),
        })
        return {"cons_total_kwh": cons_total, "exp_total_kwh": exp_total}
