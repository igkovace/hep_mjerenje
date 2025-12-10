from __future__ import annotations
import base64, csv, io
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import aiohttp, asyncio, logging

HEP_BASE = "https://mjerenje.hep.hr/mjerenja/v1/api"
_LOGGER = logging.getLogger(__name__)

class MonthNotFound(Exception):
    def __init__(self, month: str):
        super().__init__(f"Month not found: {month}")
        self.month = month

class HepMjerenjeClient:
    def __init__(self, username: str, password: str, oib: str, omm: str,
                 session: aiohttp.ClientSession, *, request_timeout: float = 30.0, max_retries: int = 3):
        self._username = username
        self._password = password
        self._oib = oib
        self._omm = omm
        self._session = session
        self._token: str | None = None
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)
        self._max_retries = max_retries

    def set_timeout(self, seconds: float):
        self._timeout = aiohttp.ClientTimeout(total=seconds)

    async def login(self) -> None:
        payload = {"Username": self._username, "Password": self._password}
        async with self._session.post(f"{HEP_BASE}/user/login", json=payload, timeout=self._timeout) as resp:
            resp.raise_for_status()
            data = await resp.json()
            self._token = data.get("Token")
            if not self._token:
                raise RuntimeError("HEP token missing in login response")

    def _auth_hdr(self) -> Dict[str, str]:
        if not self._token:
            raise RuntimeError("Not authenticated")
        return {"Authorization": f"Bearer {self._token}"}

    async def _get_month_csv_b64(self, month_str: str, direction: str) -> bytes:
        url = (f"{HEP_BASE}/data/file/oib/{self._oib}/omm/{self._omm}/"
               f"krivulja/mjesec/{month_str}/smjer/{direction}")
        attempt = 0
        last_exc: Optional[Exception] = None
        while attempt < self._max_retries:
            try:
                async with self._session.get(url, headers=self._auth_hdr(), timeout=self._timeout) as resp:
                    if resp.status == 404:
                        raise MonthNotFound(month_str)
                    if resp.status == 401:
                        _LOGGER.debug("401 for %s %s; refreshing token...", direction, month_str)
                        await self.login()
                        continue
                    if resp.status in (429, 500, 502, 503, 504):
                        raise aiohttp.ClientResponseError(resp.request_info, resp.history, status=resp.status)
                    resp.raise_for_status()
                    data = await resp.json()
                    b64 = data.get("data", "")
                    return base64.b64decode(b64) if b64 else b""
            except MonthNotFound:
                raise
            except Exception as ex:
                last_exc = ex
                delay = min(2 ** attempt + 0.1 * attempt, 5.0)
                _LOGGER.debug("GET %s attempt %d failed: %s; retry in %.1fs", url, attempt + 1, ex, delay)
                await asyncio.sleep(delay)
                attempt += 1
        if last_exc:
            _LOGGER.error("Failed to fetch %s after %d attempts: %s", url, self._max_retries, last_exc)
            raise last_exc
        return b""

    @staticmethod
    def _pad_time_hms(t: str) -> str:
        parts = t.split(":")
        if len(parts) == 3:
            h, m, s = parts
            if len(h) == 1:
                h = h.rjust(2, '0')
            return f"{h}:{m}:{s}"
        return t

    @staticmethod
    def _detect_delim_and_header(text: str):
        first = next((ln for ln in text.splitlines() if ln.strip()), '')
        delim = '\t' if ('\t' in first) else ';'
        reader = csv.reader(io.StringIO(text), delimiter=delim)
        for row in reader:
            if row:
                return delim, row
        return delim, []

    @staticmethod
    def parse_csv(raw: bytes, *, date_col: int, time_col: int, kw_col: int,
                  time_fmt: str, date_fmt: str) -> Tuple[List[Dict], bool]:
        if not raw:
            return [], False
        text = raw.decode("utf-8", errors="replace")
        delim, header = HepMjerenjeClient._detect_delim_and_header(text)
        reader = csv.reader(io.StringIO(text), delimiter=delim)
        rows: List[Dict] = []
        first = True
        for row in reader:
            if not row:
                continue
            if first:
                first = False
                continue
            try:
                d = row[date_col].strip()
                t = HepMjerenjeClient._pad_time_hms(row[time_col].strip())
                ts = datetime.strptime(f"{d} {t}", f"{date_fmt} {time_fmt}")
            except Exception:
                ts = None
                for fmt in ("%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                    try:
                        ts = datetime.strptime(f"{row[date_col]} {row[time_col]}", fmt)
                        break
                    except Exception:
                        pass
            if ts is None:
                continue
            try:
                val = float(row[kw_col].replace(',', '.').strip())
            except Exception:
                continue
            rows.append({"ts": ts, "val": val})
        if rows:
            return rows, False
        return HepMjerenjeClient.parse_csv_auto(raw, time_fmt=time_fmt, date_fmt=date_fmt)

    @staticmethod
    def parse_csv_auto(raw: bytes, *, time_fmt: str, date_fmt: str) -> Tuple[List[Dict], bool]:
        if not raw:
            return [], True
        text = raw.decode("utf-8", errors="replace")
        delim, header = HepMjerenjeClient._detect_delim_and_header(text)
        reader = csv.reader(io.StringIO(text), delimiter=delim)
        date_idx = None
        time_idx = None
        energy_idx = None
        power_idx = None
        status_idx = None
        hdr = [h.strip().lower() for h in header]
        for i, h in enumerate(hdr):
            if h in ("datum", "date"): date_idx = i
            elif h in ("vrijeme", "time"): time_idx = i
            elif "energ" in h: energy_idx = i
            elif "snaga" in h or "power" in h: power_idx = i
            elif h == "status": status_idx = i
        val_candidates = [i for i in (energy_idx, power_idx) if i is not None]
        rows: List[Dict] = []
        first = True
        for row in reader:
            if not row:
                continue
            if first:
                first = False
                continue
            ts = None
            if date_idx is not None and time_idx is not None:
                d = row[date_idx].strip()
                t = HepMjerenjeClient._pad_time_hms(row[time_idx].strip())
                for fmt in (f"{date_fmt} {time_fmt}", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                    try:
                        ts = datetime.strptime(f"{d} {t}", fmt)
                        break
                    except Exception:
                        continue
            if ts is None:
                continue
            val = None
            for idx in val_candidates:
                try:
                    val = float(row[idx].replace(',', '.').strip())
                    break
                except Exception:
                    pass
            if val is None:
                for idx in range(len(row)-1, -1, -1):
                    if status_idx is not None and idx == status_idx:
                        continue
                    cell = row[idx].replace(',', '.').strip()
                    try:
                        val = float(cell)
                        break
                    except Exception:
                        pass
            if val is None:
                continue
            rows.append({"ts": ts, "val": val})
        return rows, True

    async def get_month(self, month_str: str, *, date_col: int, time_col: int, kw_col: int,
                        time_fmt: str, date_fmt: str) -> Tuple[List[Dict], List[Dict], bool]:
        fallback_used = False
        try:
            p_raw = await self._get_month_csv_b64(month_str, "P")
        except MonthNotFound:
            p_raw = b""
        try:
            r_raw = await self._get_month_csv_b64(month_str, "R")
        except MonthNotFound:
            r_raw = b""
        p_rows, fb_p = self.parse_csv(p_raw, date_col=date_col, time_col=time_col, kw_col=kw_col, time_fmt=time_fmt, date_fmt=date_fmt)
        r_rows, fb_r = self.parse_csv(r_raw, date_col=date_col, time_col=time_col, kw_col=kw_col, time_fmt=time_fmt, date_fmt=date_fmt)
        fallback_used = fb_p or fb_r
        return p_rows, r_rows, fallback_used
