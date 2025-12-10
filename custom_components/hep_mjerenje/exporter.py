from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from typing import List, Dict
from aiohttp import ClientSession, ClientTimeout
import logging
from .const import (
    CONF_EXPORTER_ENABLED, CONF_INFLUX_URL, CONF_INFLUX_TOKEN, CONF_INFLUX_ORG, CONF_INFLUX_BUCKET,
    CONF_EXPORT_SERIES_15M, CONF_EXPORT_SERIES_DAILY, CONF_EXPORT_SERIES_MONTHLY,
)

_LOGGER = logging.getLogger(__name__)

async def export_influx(options: Dict, omm: str, p_rows: List[Dict], r_rows: List[Dict], conv_func, session: ClientSession) -> None:
    """Best-effort InfluxDB v2 export using provided HA aiohttp session."""
    if not options.get(CONF_EXPORTER_ENABLED, False):
        return
    url = options.get(CONF_INFLUX_URL)
    token = options.get(CONF_INFLUX_TOKEN)
    org = options.get(CONF_INFLUX_ORG)
    bucket = options.get(CONF_INFLUX_BUCKET)
    if not (url and token and org and bucket):
        return
    lines: List[str] = []
    meas = 'hep_energy'
    tag = 'omm=' + str(omm)
    # 15-min points
    if options.get(CONF_EXPORT_SERIES_15M, True):
        for row in p_rows:
            ts_ns = int(row['ts'].timestamp()) * 1_000_000_000
            val = conv_func(row['val'])
            lines.append(f"{meas},{tag} consumption_kwh={val} {ts_ns}")
        for row in r_rows:
            ts_ns = int(row['ts'].timestamp()) * 1_000_000_000
            val = conv_func(row['val'])
            lines.append(f"{meas},{tag} export_kwh={val} {ts_ns}")
    # group by day
    if options.get(CONF_EXPORT_SERIES_DAILY, True):
        day_c: Dict = defaultdict(float)
        day_r: Dict = defaultdict(float)
        for row in p_rows:
            day_c[row['ts'].date()] += conv_func(row['val'])
        for row in r_rows:
            day_r[row['ts'].date()] += conv_func(row['val'])
        for d in sorted(set(list(day_c.keys()) + list(day_r.keys()))):
            ts_ns = int(datetime(d.year, d.month, d.day).timestamp()) * 1_000_000_000
            c = day_c.get(d, 0.0)
            r = day_r.get(d, 0.0)
            lines.append(f"{meas},{tag},granularity=daily consumption_kwh={c},export_kwh={r} {ts_ns}")
    # monthly aggregate (single point at 1st of month)
    if options.get(CONF_EXPORT_SERIES_MONTHLY, True) and p_rows:
        dt0 = p_rows[0]['ts']
        month_ts = int(datetime(dt0.year, dt0.month, 1).timestamp()) * 1_000_000_000
        c_sum = sum(conv_func(r['val']) for r in p_rows)
        r_sum = sum(conv_func(r['val']) for r in r_rows)
        lines.append(f"{meas},{tag},granularity=monthly consumption_kwh={c_sum},export_kwh={r_sum} {month_ts}")
    write_url = url.rstrip('/') + f"/api/v2/write?org={org}&bucket={bucket}&precision=ns"
    headers = {
        'Authorization': 'Token ' + token,
        'Content-Type': 'text/plain; charset=utf-8',
    }
    payload = "\n".join(lines).encode('utf-8')
    async with session.post(write_url, data=payload, headers=headers, timeout=ClientTimeout(total=20)) as resp:
        if resp.status >= 400:
            txt = await resp.text()
            _LOGGER.debug("Influx payload preview:\n%s", payload.decode("utf-8")[:512])
            raise RuntimeError(f"Influx write failed: {resp.status} {txt}")
