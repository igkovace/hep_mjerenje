
from __future__ import annotations
import base64
import csv
import io
from datetime import datetime
from typing import List, Dict, Tuple
import aiohttp

HEP_BASE = "https://mjerenje.hep.hr/mjerenja/v1/api"

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
            if resp.status == 401:
                await self.login()
                async with self._session.get(url, headers=self._auth_hdr()) as resp2:
                    resp2.raise_for_status()
                    data = await resp2.json()
            else:
                resp.raise_for_status()
                data = await resp.json()
        b64 = data.get("data", "")
        return base64.b64decode(b64)

    @staticmethod
    def parse_csv(raw: bytes) -> List[Dict]:
        text = raw.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text), delimiter=';')
        rows: List[Dict] = []
        header = None
        for row in reader:
            if not row:
                continue
            if header is None:
                header = row
                continue
            # Try common datetime formats
            ts = None
            for fmt in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"):
                try:
                    ts = datetime.strptime(row[0], fmt)
                    break
                except Exception:
                    pass
            if ts is None:
                continue
            # Heuristic: last numeric column is kW
            kw = None
            for cell in reversed(row):
                c = cell.replace(',', '.')
                try:
                    kw = float(c)
                    break
                except Exception:
                    continue
            if kw is None:
                continue
            rows.append({"ts": ts, "kw": kw})
        return rows

    async def get_month(self, month_str: str) -> Tuple[List[Dict], List[Dict]]:
        p_raw = await self._get_month_csv_b64(month_str, "P")
        r_raw = await self._get_month_csv_b64(month_str, "R")
        p_rows = self.parse_csv(p_raw)
        r_rows = self.parse_csv(r_raw)
        return p_rows, r_rows
