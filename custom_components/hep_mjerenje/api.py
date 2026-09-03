from __future__ import annotations

import base64
import csv
import io
import logging
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import asyncio

HEP_ROOT = "https://mjerenje.hep.hr"
HEP_BASE = f"{HEP_ROOT}/mjerenja/v1/api"
LOGIN_URL = f"{HEP_BASE}/user/login"

_LOGGER = logging.getLogger(__name__)


class MonthNotFound(Exception):
    def __init__(self, month: str):
        super().__init__(f"Month not found: {month}")
        self.month = month


class HepMjerenjeClient:
    def __init__(
        self,
        username: str,
        password: str,
        oib: str,
        omm: str,
        session: aiohttp.ClientSession,
        *,
        request_timeout: float = 30.0,
        max_retries: int = 3,
    ):
        self._username = username
        self._password = password
        self._oib = str(oib).strip()
        self._omm = str(omm).strip()
        self._session = session
        self._token: str | None = None
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)
        self._max_retries = max_retries

    def set_timeout(self, seconds: float):
        self._timeout = aiohttp.ClientTimeout(total=seconds)

    async def login(self) -> None:
        payload = {
            "Username": self._username,
            "Password": self._password,
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": HEP_ROOT,
            "Referer": f"{HEP_ROOT}/mjerenja/login",
            "User-Agent": "Mozilla/5.0",
        }

        async with self._session.post(
            LOGIN_URL,
            json=payload,
            headers=headers,
            timeout=self._timeout,
        ) as resp:
            text = await resp.text()

            if resp.status != 200:
                _LOGGER.error("HEP login failed with status %s: %s", resp.status, text[:1000])
                resp.raise_for_status()

            try:
                data = await resp.json(content_type=None)
            except Exception:
                _LOGGER.error("HEP login returned non-JSON response: %s", text[:1000])
                raise

            self._token = self._extract_token(data)

            if not self._token:
                _LOGGER.error("HEP token missing in login response: %s", str(data)[:1000])
                raise RuntimeError("HEP token missing in login response")

            _LOGGER.debug("HEP login successful")

    @staticmethod
    def _extract_token(data: Any) -> str | None:
        token_keys = {
            "Token",
            "token",
            "accessToken",
            "access_token",
            "jwt",
            "JWT",
            "idToken",
            "id_token",
        }

        if isinstance(data, dict):
            for key in token_keys:
                value = data.get(key)
                if value:
                    return str(value)

            for value in data.values():
                found = HepMjerenjeClient._extract_token(value)
                if found:
                    return found

        if isinstance(data, list):
            for item in data:
                found = HepMjerenjeClient._extract_token(item)
                if found:
                    return found

        if isinstance(data, str):
            stripped = data.strip()
            if len(stripped) > 20 and ("." in stripped or len(stripped) > 40):
                return stripped

        return None

    def _auth_hdr(self) -> Dict[str, str]:
        if not self._token:
            raise RuntimeError("Not authenticated")

        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": HEP_ROOT,
            "Referer": f"{HEP_ROOT}/mjerenja/",
            "User-Agent": "Mozilla/5.0",
        }

    async def _get_month_file(self, month_str: str, direction: str) -> bytes:
        url = (
            f"{HEP_BASE}/data/file/oib/{self._oib}/omm/{self._omm}/"
            f"krivulja/mjesec/{month_str}/smjer/{direction}"
        )

        attempt = 0
        last_exc: Optional[Exception] = None

        while attempt < self._max_retries:
            try:
                # HEP v1 data/file endpoint now expects POST and returns an XLSX file directly.
                async with self._session.post(
                    url,
                    headers=self._auth_hdr(),
                    timeout=self._timeout,
                ) as resp:
                    body = await resp.read()
                    text_preview = body[:1000].decode("utf-8", errors="replace")
                    content_type = resp.headers.get("Content-Type", "").lower()

                    if resp.status == 404:
                        raise MonthNotFound(month_str)

                    if resp.status == 400:
                        # HEP often returns this for months that are not available yet.
                        _LOGGER.debug(
                            "HEP data not available for %s %s: %s",
                            direction,
                            month_str,
                            text_preview,
                        )
                        raise MonthNotFound(month_str)

                    if resp.status == 401:
                        _LOGGER.debug("401 for %s %s; refreshing token...", direction, month_str)
                        self._token = None
                        await self.login()
                        attempt += 1
                        continue

                    if resp.status in (429, 500, 502, 503, 504):
                        raise aiohttp.ClientResponseError(
                            resp.request_info,
                            resp.history,
                            status=resp.status,
                            message=text_preview,
                        )

                    if resp.status != 200:
                        _LOGGER.error("HEP data endpoint returned status %s: %s", resp.status, text_preview)
                        resp.raise_for_status()

                    # Current HEP behavior: 200 with application/vnd.openxmlformats...
                    if (
                        "spreadsheetml.sheet" in content_type
                        or body.startswith(b"PK\x03\x04")
                    ):
                        return body

                    # Backward compatibility: older API returned JSON with base64 in data.
                    try:
                        data = await resp.json(content_type=None)
                    except Exception:
                        _LOGGER.error(
                            "HEP data endpoint returned unsupported content type %s: %s",
                            content_type,
                            text_preview,
                        )
                        raise

                    if isinstance(data, dict):
                        b64 = data.get("data") or data.get("Data") or ""
                        if b64:
                            return base64.b64decode(b64)

                    return b""

            except MonthNotFound:
                raise
            except Exception as ex:
                last_exc = ex
                delay = min(2 ** attempt + 0.1 * attempt, 5.0)
                _LOGGER.debug(
                    "POST %s attempt %d failed: %s; retry in %.1fs",
                    url,
                    attempt + 1,
                    ex,
                    delay,
                )
                await asyncio.sleep(delay)
                attempt += 1

        if last_exc:
            _LOGGER.error(
                "Failed to fetch %s after %d attempts: %s",
                url,
                self._max_retries,
                last_exc,
            )
            raise last_exc

        return b""

    @staticmethod
    def _pad_time_hms(t: str) -> str:
        parts = t.split(":")
        if len(parts) == 3:
            h, m, s = parts
            if len(h) == 1:
                h = h.rjust(2, "0")
            return f"{h}:{m}:{s}"
        return t

    @staticmethod
    def _detect_delim_and_header(text: str):
        first = next((ln for ln in text.splitlines() if ln.strip()), "")
        delim = "\t" if ("\t" in first) else ";"
        reader = csv.reader(io.StringIO(text), delimiter=delim)
        for row in reader:
            if row:
                return delim, row
        return delim, []

    @staticmethod
    def _xlsx_shared_strings(zf: zipfile.ZipFile) -> List[str]:
        try:
            raw = zf.read("xl/sharedStrings.xml")
        except KeyError:
            return []

        root = ET.fromstring(raw)
        ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        strings: List[str] = []

        for si in root.findall("a:si", ns):
            parts = []
            for t in si.findall(".//a:t", ns):
                parts.append(t.text or "")
            strings.append("".join(parts))

        return strings

    @staticmethod
    def _xlsx_sheet_rows(raw: bytes) -> List[List[str]]:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            shared = HepMjerenjeClient._xlsx_shared_strings(zf)

            sheet_name = "xl/worksheets/sheet1.xml"
            if sheet_name not in zf.namelist():
                sheets = [n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
                if not sheets:
                    return []
                sheet_name = sorted(sheets)[0]

            root = ET.fromstring(zf.read(sheet_name))
            ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            rows: List[List[str]] = []

            for row in root.findall(".//a:sheetData/a:row", ns):
                values: List[str] = []
                last_col = 0

                for cell in row.findall("a:c", ns):
                    ref = cell.attrib.get("r", "")
                    col_letters = "".join(ch for ch in ref if ch.isalpha())
                    if col_letters:
                        col_num = 0
                        for ch in col_letters:
                            col_num = col_num * 26 + (ord(ch.upper()) - ord("A") + 1)
                        while last_col < col_num - 1:
                            values.append("")
                            last_col += 1

                    cell_type = cell.attrib.get("t")
                    value_el = cell.find("a:v", ns)
                    inline_el = cell.find(".//a:t", ns)

                    value = ""
                    if cell_type == "inlineStr" and inline_el is not None:
                        value = inline_el.text or ""
                    elif value_el is not None:
                        raw_value = value_el.text or ""
                        if cell_type == "s":
                            try:
                                value = shared[int(raw_value)]
                            except Exception:
                                value = raw_value
                        else:
                            value = raw_value

                    values.append(value)
                    last_col += 1

                if any(str(v).strip() for v in values):
                    rows.append(values)

            return rows

    @staticmethod
    def _excel_serial_to_datetime(value: str) -> datetime | None:
        try:
            serial = float(str(value).replace(",", "."))
        except Exception:
            return None

        # Excel date serial, Windows epoch with 1900 leap-year bug compatibility.
        try:
            return datetime.fromordinal(datetime(1899, 12, 30).toordinal() + int(serial)) \
                .replace(hour=0, minute=0, second=0, microsecond=0)
        except Exception:
            return None

    @staticmethod
    def _parse_datetime_values(date_value: str, time_value: str, *, date_fmt: str, time_fmt: str) -> datetime | None:
        d = str(date_value).strip()
        t = HepMjerenjeClient._pad_time_hms(str(time_value).strip())

        for fmt in (
            f"{date_fmt} {time_fmt}",
            "%d.%m.%Y %H:%M",
            "%d.%m.%Y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ):
            try:
                return datetime.strptime(f"{d} {t}", fmt)
            except Exception:
                pass

        # HEP XLSX may store Croatian dates as compact numeric text:
        # 1052026 = 1.05.2026, 31052026 = 31.05.2026.
        compact = "".join(ch for ch in d if ch.isdigit())
        compact_dt = None
        try:
            if len(compact) == 7:
                compact_dt = datetime(int(compact[3:7]), int(compact[1:3]), int(compact[0:1]))
            elif len(compact) == 8:
                compact_dt = datetime(int(compact[4:8]), int(compact[2:4]), int(compact[0:2]))
        except Exception:
            compact_dt = None

        if compact_dt is not None:
            for tfmt in ("%H:%M:%S", "%H:%M"):
                try:
                    parsed_time = datetime.strptime(t, tfmt).time()
                    return compact_dt.replace(
                        hour=parsed_time.hour,
                        minute=parsed_time.minute,
                        second=parsed_time.second,
                    )
                except Exception:
                    pass
            try:
                frac = float(str(t).replace(",", "."))
                seconds = int(round(frac * 86400))
                return compact_dt + timedelta(seconds=seconds)
            except Exception:
                return compact_dt

        # XLSX may store date/time as Excel serials.
        date_dt = HepMjerenjeClient._excel_serial_to_datetime(d)
        if date_dt is not None:
            try:
                frac = float(str(t).replace(",", "."))
                seconds = int(round(frac * 86400))
                return date_dt.replace(hour=0, minute=0, second=0) + timedelta(seconds=seconds)
            except Exception:
                return date_dt

        return None

    @staticmethod
    def parse_xlsx(
        raw: bytes,
        *,
        date_col: int,
        time_col: int,
        kw_col: int,
        time_fmt: str,
        date_fmt: str,
    ) -> Tuple[List[Dict], bool]:
        rows_raw = HepMjerenjeClient._xlsx_sheet_rows(raw)
        if not rows_raw:
            return [], True

        # Prefer the energy column when present. In HEP XLSX, column
        # "Vrijednost snaga" is kW power, while "Vrijednost energija" is kWh.
        # The old integration constant may point to the power column, causing
        # totals to be about 4x too high for 15-minute intervals.
        header = [str(h).strip().lower() for h in rows_raw[0]]
        energy_col = None
        for idx, name in enumerate(header):
            if "energ" in name:
                energy_col = idx
                break

        value_col = energy_col if energy_col is not None else kw_col

        # Drop header row. The integration constants are zero-based column indexes.
        data_rows = rows_raw[1:] if len(rows_raw) > 1 else []
        rows: List[Dict] = []

        for row in data_rows:
            try:
                date_value = row[date_col] if date_col < len(row) else ""
                time_value = row[time_col] if time_col < len(row) else ""
                val_value = row[value_col] if value_col < len(row) else ""
            except Exception:
                continue

            ts = HepMjerenjeClient._parse_datetime_values(
                date_value,
                time_value,
                date_fmt=date_fmt,
                time_fmt=time_fmt,
            )
            if ts is None:
                continue

            try:
                val = float(str(val_value).replace(",", ".").strip())
            except Exception:
                continue

            rows.append({"ts": ts, "val": val})

        if rows:
            return rows, False

        return HepMjerenjeClient.parse_xlsx_auto(
            raw,
            time_fmt=time_fmt,
            date_fmt=date_fmt,
        )

    @staticmethod
    def parse_xlsx_auto(raw: bytes, *, time_fmt: str, date_fmt: str) -> Tuple[List[Dict], bool]:
        rows_raw = HepMjerenjeClient._xlsx_sheet_rows(raw)
        if len(rows_raw) < 2:
            return [], True

        header = [str(h).strip().lower() for h in rows_raw[0]]

        date_idx = None
        time_idx = None
        energy_idx = None
        power_idx = None
        status_idx = None

        for i, h in enumerate(header):
            if h in ("datum", "date"):
                date_idx = i
            elif h in ("vrijeme", "time"):
                time_idx = i
            elif "energ" in h:
                energy_idx = i
            elif "snaga" in h or "power" in h:
                power_idx = i
            elif h == "status":
                status_idx = i

        val_candidates = [i for i in (energy_idx, power_idx) if i is not None]
        rows: List[Dict] = []

        for row in rows_raw[1:]:
            if date_idx is None or time_idx is None:
                continue

            date_value = row[date_idx] if date_idx < len(row) else ""
            time_value = row[time_idx] if time_idx < len(row) else ""

            ts = HepMjerenjeClient._parse_datetime_values(
                date_value,
                time_value,
                date_fmt=date_fmt,
                time_fmt=time_fmt,
            )
            if ts is None:
                continue

            val = None
            for idx in val_candidates:
                if idx < len(row):
                    try:
                        val = float(str(row[idx]).replace(",", ".").strip())
                        break
                    except Exception:
                        pass

            if val is None:
                for idx in range(len(row) - 1, -1, -1):
                    if status_idx is not None and idx == status_idx:
                        continue
                    try:
                        val = float(str(row[idx]).replace(",", ".").strip())
                        break
                    except Exception:
                        pass

            if val is None:
                continue

            rows.append({"ts": ts, "val": val})

        return rows, True

    @staticmethod
    def parse_csv(
        raw: bytes,
        *,
        date_col: int,
        time_col: int,
        kw_col: int,
        time_fmt: str,
        date_fmt: str,
    ) -> Tuple[List[Dict], bool]:
        if not raw:
            return [], False

        if raw.startswith(b"PK\x03\x04"):
            return HepMjerenjeClient.parse_xlsx(
                raw,
                date_col=date_col,
                time_col=time_col,
                kw_col=kw_col,
                time_fmt=time_fmt,
                date_fmt=date_fmt,
            )

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
                ts = HepMjerenjeClient._parse_datetime_values(
                    row[date_col],
                    row[time_col],
                    date_fmt=date_fmt,
                    time_fmt=time_fmt,
                )
            except Exception:
                ts = None

            if ts is None:
                continue

            try:
                val = float(row[kw_col].replace(",", ".").strip())
            except Exception:
                continue

            rows.append({"ts": ts, "val": val})

        if rows:
            return rows, False

        return HepMjerenjeClient.parse_csv_auto(
            raw,
            time_fmt=time_fmt,
            date_fmt=date_fmt,
        )

    @staticmethod
    def parse_csv_auto(
        raw: bytes,
        *,
        time_fmt: str,
        date_fmt: str,
    ) -> Tuple[List[Dict], bool]:
        if not raw:
            return [], True

        if raw.startswith(b"PK\x03\x04"):
            return HepMjerenjeClient.parse_xlsx_auto(
                raw,
                time_fmt=time_fmt,
                date_fmt=date_fmt,
            )

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
            if h in ("datum", "date"):
                date_idx = i
            elif h in ("vrijeme", "time"):
                time_idx = i
            elif "energ" in h:
                energy_idx = i
            elif "snaga" in h or "power" in h:
                power_idx = i
            elif h == "status":
                status_idx = i

        val_candidates = [i for i in (energy_idx, power_idx) if i is not None]
        rows: List[Dict] = []
        first = True

        for row in reader:
            if not row:
                continue

            if first:
                first = False
                continue

            if date_idx is None or time_idx is None:
                continue

            ts = HepMjerenjeClient._parse_datetime_values(
                row[date_idx],
                row[time_idx],
                date_fmt=date_fmt,
                time_fmt=time_fmt,
            )

            if ts is None:
                continue

            val = None

            for idx in val_candidates:
                try:
                    val = float(row[idx].replace(",", ".").strip())
                    break
                except Exception:
                    pass

            if val is None:
                for idx in range(len(row) - 1, -1, -1):
                    if status_idx is not None and idx == status_idx:
                        continue

                    cell = row[idx].replace(",", ".").strip()
                    try:
                        val = float(cell)
                        break
                    except Exception:
                        pass

            if val is None:
                continue

            rows.append({"ts": ts, "val": val})

        return rows, True

    async def get_month(
        self,
        month_str: str,
        *,
        date_col: int,
        time_col: int,
        kw_col: int,
        time_fmt: str,
        date_fmt: str,
    ) -> Tuple[List[Dict], List[Dict], bool]:
        fallback_used = False

        try:
            p_raw = await self._get_month_file(month_str, "P")
        except MonthNotFound:
            p_raw = b""

        try:
            r_raw = await self._get_month_file(month_str, "R")
        except MonthNotFound:
            r_raw = b""

        p_rows, fb_p = self.parse_csv(
            p_raw,
            date_col=date_col,
            time_col=time_col,
            kw_col=kw_col,
            time_fmt=time_fmt,
            date_fmt=date_fmt,
        )

        r_rows, fb_r = self.parse_csv(
            r_raw,
            date_col=date_col,
            time_col=time_col,
            kw_col=kw_col,
            time_fmt=time_fmt,
            date_fmt=date_fmt,
        )

        fallback_used = fb_p or fb_r

        return p_rows, r_rows, fallback_used
