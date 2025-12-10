from __future__ import annotations
import logging, asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.helpers import aiohttp_client

from .const import (
    KEY_CONS_TOTAL, KEY_EXP_TOTAL,
    KEY_CONS_MONTH, KEY_EXP_MONTH,
    KEY_CONS_YESTERDAY, KEY_EXP_YESTERDAY,
    KEY_CONS_PREV_MONTH, KEY_EXP_PREV_MONTH,
    KEY_CONS_YEAR, KEY_EXP_YEAR,
    KEY_DIAG_ROWS, KEY_DIAG_CUR_ROWS, KEY_DIAG_PREV_ROWS, KEY_DIAG_LAST_TS_P, KEY_DIAG_LAST_TS_R, KEY_DIAG_SUM_P, KEY_DIAG_SUM_R, KEY_DIAG_SKIPPED_MONTHS, KEY_DIAG_FALLBACK_USED,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    FIXED_DATE_COL, FIXED_TIME_COL, FIXED_KW_COL, FIXED_TIME_FMT, FIXED_DATE_FMT, FIXED_VALUE_IS_ENERGY,
    PERSIST_IMPORTED_MONTHS,
    CONF_SYNC_TOTAL_TO_YTD,
    CONF_UPDATE_INTERVAL_MINUTES, DEFAULT_UPDATE_INTERVAL_MINUTES,
    CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT,
    CONF_MAX_CONCURRENCY, DEFAULT_MAX_CONCURRENCY,
)
from .api import HepMjerenjeClient

_LOGGER = logging.getLogger(__name__)

class HepCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, client: HepMjerenjeClient, omm: str, store_key: str):
        super().__init__(
            hass,
            _LOGGER,
            name="HEP Mjerenje",
            update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES),
        )
        self._client = client
        self._omm = omm
        self._store = Store(hass, 1, f"hep_mjerenje_totals_{store_key}")
        self._persist: Dict = {}
        self._options: Dict = {}
        self._lock = asyncio.Lock()
        self._ytd_cache: Optional[Dict[str, float]] = None
        self._ytd_cache_date: Optional[datetime] = None
        self._max_concurrency: int = DEFAULT_MAX_CONCURRENCY

    async def _load_persist(self):
        self._persist = await self._store.async_load() or {"cons_total": 0.0, "exp_total": 0.0, PERSIST_IMPORTED_MONTHS: []}
        if not isinstance(self._persist.get(PERSIST_IMPORTED_MONTHS), list):
            self._persist[PERSIST_IMPORTED_MONTHS] = []

    async def _save_persist(self):
        await self._store.async_save(self._persist)

    async def reset_persist(self):
        self._persist = {"cons_total": 0.0, "exp_total": 0.0, PERSIST_IMPORTED_MONTHS: []}
        await self._save_persist()
        self.async_set_updated_data({
            KEY_CONS_TOTAL: 0.0,
            KEY_EXP_TOTAL: 0.0,
            KEY_CONS_MONTH: 0.0,
            KEY_EXP_MONTH: 0.0,
            KEY_CONS_YESTERDAY: 0.0,
            KEY_EXP_YESTERDAY: 0.0,
            KEY_CONS_PREV_MONTH: 0.0,
            KEY_EXP_PREV_MONTH: 0.0,
            KEY_CONS_YEAR: 0.0,
            KEY_EXP_YEAR: 0.0,
            KEY_DIAG_ROWS: 0,
            KEY_DIAG_CUR_ROWS: 0,
            KEY_DIAG_PREV_ROWS: 0,
            KEY_DIAG_LAST_TS_P: None,
            KEY_DIAG_LAST_TS_R: None,
            KEY_DIAG_SUM_P: 0.0,
            KEY_DIAG_SUM_R: 0.0,
            KEY_DIAG_SKIPPED_MONTHS: None,
            KEY_DIAG_FALLBACK_USED: False,
            "last_update": datetime.utcnow().isoformat(),
        })

    async def clear_import_cache(self):
        if not self._persist:
            await self._load_persist()
        self._persist[PERSIST_IMPORTED_MONTHS] = []
        await self._save_persist()

    def set_options(self, options: Dict):
        self._options = options or {}
        # Advanced options
        interval_min = int(self._options.get(CONF_UPDATE_INTERVAL_MINUTES, DEFAULT_UPDATE_INTERVAL_MINUTES))
        self.update_interval = timedelta(minutes=interval_min)
        req_timeout = float(self._options.get(CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT))
        try:
            self._client.set_timeout(req_timeout)
        except Exception:
            pass
        self._max_concurrency = int(self._options.get(CONF_MAX_CONCURRENCY, DEFAULT_MAX_CONCURRENCY))

    def _conv(self, v: float) -> float:
        # Values are energy (kWh) by design
        return v

    async def _fetch_month(self, month_str: str) -> Tuple[List[Dict], List[Dict], bool, str | None]:
        try:
            p_rows, r_rows, fb = await self._client.get_month(
                month_str,
                date_col=FIXED_DATE_COL,
                time_col=FIXED_TIME_COL,
                kw_col=FIXED_KW_COL,
                time_fmt=FIXED_TIME_FMT,
                date_fmt=FIXED_DATE_FMT,
            )
            return p_rows, r_rows, fb, None
        except Exception as ex:
            _LOGGER.warning("Skipping month %s due to error: %s", month_str, ex)
            return [], [], False, month_str

    @staticmethod
    def _month_string(dt) -> str:
        return dt.strftime("%m.%Y")

    async def _async_update_data(self) -> Dict:
        async with self._lock:
            try:
                await self._client.login()
            except Exception as ex:
                _LOGGER.debug("Initial login failed (will retry on request): %s", ex)
        if not self._persist:
            await self._load_persist()

        local_now = dt_util.now()
        today = local_now.date()
        yesterday = today - timedelta(days=1)
        this_month_str = self._month_string(local_now)
        prev_month_dt = (local_now.replace(day=1) - timedelta(days=1))
        prev_month_str = self._month_string(prev_month_dt)
        conv = self._conv
        diag_skipped = []
        diag_fallback = False

        # Current month
        p_rows, r_rows, fb, sk = await self._fetch_month(this_month_str)
        if sk: diag_skipped.append(sk)
        diag_fallback = diag_fallback or fb
        for r in p_rows:
            if r['ts'].tzinfo is None:
                r['ts'] = dt_util.as_local(r['ts'])
        for r in r_rows:
            if r['ts'].tzinfo is None:
                r['ts'] = dt_util.as_local(r['ts'])
        cons_month_kwh = sum(conv(r['val']) for r in p_rows)
        exp_month_kwh = sum(conv(r['val']) for r in r_rows)
        cur_rows = len(p_rows) + len(r_rows)

        # Yesterday
        cons_yday_kwh = sum(conv(r['val']) for r in p_rows if r['ts'].date() == yesterday)
        exp_yday_kwh = sum(conv(r['val']) for r in r_rows if r['ts'].date() == yesterday)

        # Previous month
        p_prev, r_prev, fb2, sk2 = await self._fetch_month(prev_month_str)
        if sk2: diag_skipped.append(sk2)
        diag_fallback = diag_fallback or fb2
        for r in p_prev:
            if r['ts'].tzinfo is None:
                r['ts'] = dt_util.as_local(r['ts'])
        for r in r_prev:
            if r['ts'].tzinfo is None:
                r['ts'] = dt_util.as_local(r['ts'])
        cons_prev_month_kwh = sum(conv(r['val']) for r in p_prev)
        exp_prev_month_kwh = sum(conv(r['val']) for r in r_prev)
        prev_rows = len(p_prev) + len(r_prev)

        # YTD cache (once per day)
        if self._ytd_cache is None or (self._ytd_cache_date and self._ytd_cache_date.date() != today):
            cons_year = 0.0
            exp_year = 0.0
            y_start = local_now.replace(month=1, day=1)
            ptr = y_start
            safety = 0
            while ptr.month <= local_now.month and safety < 24:
                m_str = self._month_string(ptr)
                p_m, r_m, fb_m, sk_m = await self._fetch_month(m_str)
                if sk_m:
                    diag_skipped.append(sk_m)
                else:
                    for r in p_m:
                        if r['ts'].tzinfo is None:
                            r['ts'] = dt_util.as_local(r['ts'])
                    for r in r_m:
                        if r['ts'].tzinfo is None:
                            r['ts'] = dt_util.as_local(r['ts'])
                    cons_year += sum(conv(r['val']) for r in p_m)
                    exp_year += sum(conv(r['val']) for r in r_m)
                diag_fallback = diag_fallback or fb_m
                if ptr.month == 12:
                    break
                ptr = ptr.replace(month=ptr.month+1)
                safety += 1
            self._ytd_cache = {"cons": cons_year, "exp": exp_year}
            self._ytd_cache_date = local_now
        else:
            cons_year = self._ytd_cache["cons"]
            exp_year = self._ytd_cache["exp"]

        # Ensure lifetime totals are never smaller than YTD
        if self._options.get(CONF_SYNC_TOTAL_TO_YTD, True):
            lt_cons = float(self._persist.get('cons_total', 0.0))
            lt_exp = float(self._persist.get('exp_total', 0.0))
            updated = False
            if cons_year > lt_cons:
                self._persist['cons_total'] = cons_year
                updated = True
            if exp_year > lt_exp:
                self._persist['exp_total'] = exp_year
                updated = True
            if updated:
                await self._save_persist()

        diag_rows = cur_rows
        last_ts_p = p_rows[-1]['ts'].isoformat() if p_rows else None
        last_ts_r = r_rows[-1]['ts'].isoformat() if r_rows else None
        data = {
            KEY_CONS_TOTAL: float(self._persist.get('cons_total', 0.0)),
            KEY_EXP_TOTAL: float(self._persist.get('exp_total', 0.0)),
            KEY_CONS_MONTH: cons_month_kwh,
            KEY_EXP_MONTH: exp_month_kwh,
            KEY_CONS_YESTERDAY: cons_yday_kwh,
            KEY_EXP_YESTERDAY: exp_yday_kwh,
            KEY_CONS_PREV_MONTH: cons_prev_month_kwh,
            KEY_EXP_PREV_MONTH: exp_prev_month_kwh,
            KEY_CONS_YEAR: cons_year,
            KEY_EXP_YEAR: exp_year,
            KEY_DIAG_ROWS: diag_rows,
            KEY_DIAG_CUR_ROWS: cur_rows,
            KEY_DIAG_PREV_ROWS: prev_rows,
            KEY_DIAG_LAST_TS_P: last_ts_p,
            KEY_DIAG_LAST_TS_R: last_ts_r,
            KEY_DIAG_SUM_P: cons_month_kwh,
            KEY_DIAG_SUM_R: exp_month_kwh,
            KEY_DIAG_SKIPPED_MONTHS: ",".join(sorted(set(diag_skipped))) if diag_skipped else None,
            KEY_DIAG_FALLBACK_USED: diag_fallback,
            "last_update": datetime.utcnow().isoformat(),
        }
        try:
            from .exporter import export_influx
            session = aiohttp_client.async_get_clientsession(self.hass)
            await export_influx(self._options, self._omm, p_rows, r_rows, conv, session)
        except Exception as ex:
            _LOGGER.warning("Influx export failed: %s", ex)
        return data

    async def import_history(self, month_list: List[str], *, force: bool = False) -> Dict:
        async with self._lock:
            await self._client.login()
            if not self._persist:
                await self._load_persist()
            conv = self._conv
            imported = set(self._persist.get(PERSIST_IMPORTED_MONTHS, []))
            todo = month_list if force else [m for m in month_list if m not in imported]
            sem = asyncio.Semaphore(self._max_concurrency)
            add_c = 0.0
            add_r = 0.0
            async def _fetch(m: str):
                async with sem:
                    p_rows, r_rows, fb, sk = await self._fetch_month(m)
                    if sk:
                        return None
                    for r in p_rows:
                        if r['ts'].tzinfo is None:
                            r['ts'] = dt_util.as_local(r['ts'])
                    for r in r_rows:
                        if r['ts'].tzinfo is None:
                            r['ts'] = dt_util.as_local(r['ts'])
                    cons = sum(conv(r['val']) for r in p_rows)
                    exp = sum(conv(r['val']) for r in r_rows)
                    return (m, cons, exp)
            results = await asyncio.gather(*[_fetch(m) for m in todo])
            for res in results:
                if not res:
                    continue
                m, cons, exp = res
                add_c += cons
                add_r += exp
                if not force:
                    if PERSIST_IMPORTED_MONTHS not in self._persist:
                        self._persist[PERSIST_IMPORTED_MONTHS] = []
                    if m not in self._persist[PERSIST_IMPORTED_MONTHS]:
                        self._persist[PERSIST_IMPORTED_MONTHS].append(m)
            self._persist['cons_total'] = float(self._persist.get('cons_total', 0.0)) + add_c
            self._persist['exp_total'] = float(self._persist.get('exp_total', 0.0)) + add_r
            await self._save_persist()
            self.async_set_updated_data({
                KEY_CONS_TOTAL: self._persist['cons_total'],
                KEY_EXP_TOTAL: self._persist['exp_total'],
                KEY_CONS_MONTH: 0.0,
                KEY_EXP_MONTH: 0.0,
                KEY_CONS_YESTERDAY: 0.0,
                KEY_EXP_YESTERDAY: 0.0,
                KEY_CONS_PREV_MONTH: 0.0,
                KEY_EXP_PREV_MONTH: 0.0,
                KEY_CONS_YEAR: self._persist['cons_total'],
                KEY_EXP_YEAR: self._persist['exp_total'],
                KEY_DIAG_ROWS: 0,
                KEY_DIAG_CUR_ROWS: 0,
                KEY_DIAG_PREV_ROWS: 0,
                KEY_DIAG_LAST_TS_P: None,
                KEY_DIAG_LAST_TS_R: None,
                KEY_DIAG_SUM_P: self._persist['cons_total'],
                KEY_DIAG_SUM_R: self._persist['exp_total'],
                KEY_DIAG_SKIPPED_MONTHS: None,
                KEY_DIAG_FALLBACK_USED: False,
                "last_update": datetime.utcnow().isoformat(),
            })
            return {"cons_total_kwh": self._persist['cons_total'], "exp_total_kwh": self._persist['exp_total']}

    async def import_years(self, year_list: List[str], *, force: bool = False) -> Dict:
        months: List[str] = []
        now_dt = dt_util.utcnow()
        cur_y = now_dt.year
        cur_m = now_dt.month
        for y_str in year_list:
            try:
                y = int(str(y_str))
            except Exception:
                continue
            for m in range(1, 12+1):
                if y == cur_y and m > cur_m:
                    break
                months.append(f"{m:02d}.{y}")
        return await self.import_history(months, force=force)
