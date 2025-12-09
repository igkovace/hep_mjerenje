
from __future__ import annotations
import base64
import csv
import io
from datetime import datetime
from typing import List, Dict, Tuple
import aiohttp

HEP_BASE = "https://mjerenje.hep.hr/mjerenja/v1/api"

class MonthNotFound(Exception):
    def __init__(self, month: str):
        super().__init__(f"Month not found: {month}")
        self.month = month

class HepMjerenjeClient:
    def __init__(self, username: str, password: str, oib: str, omm: str, session: aiohttp.ClientSession):
        self._username = username
        self._password = password
        self._oib = oib
        self._omm = omm
        self._session = session
        self._token: str | None = None

    async def login(self) -> None:
        payload = {"Username": self._username, "Password": self._password}
        async with self._session.post(f"{HEP_BASE}/user/login", json=payload) as resp:
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
        async with self._session.get(url, headers=self._auth_hdr()) as resp:
            if resp.status == 404:
                raise MonthNotFound(month_str)
            if resp.status == 401:
                await self.login()
                async with self._session.get(url, headers=self._auth_hdr()) as resp2:
                    if resp2.status == 404:
                        raise MonthNotFound(month_str)
                    resp2.raise_for_status()
                    data = await resp2.json()
            else:
                resp.raise_for_status()
                data = await resp.json()
        b64 = data.get("data", "")
        if not b64:
            return b""
        return base64.b64decode(b64)

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
        delim = '	' if ('	' in first) else ';'
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
