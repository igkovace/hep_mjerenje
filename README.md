![GitHub](https://img.shields.io/badge/GitHub-100000?logo=github&logoColor=white)
![Python](https://img.shields.io/badge/Python-14354C?style=flat&logo=python&logoColor=white)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/igkovace/hep-ods-mjerenje)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

# HEP ODS Mjerenje – Home Assistant Custom Integration

## About
This integration pulls [HEP ODS Mjerenje](https://mjerenje.hep.hr/)'s API 15‑minute power curves from the HEP ODS "Mjerenje" portal and exposes energy sensors suitable for Home Assistant Energy Dashboard.
Supports historical backfill and optional InfluxDB v2 export.

## Installation
## 1. Easy Mode (HACS)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
Installation of HACS (Recommended)

1. Install HACS if you don't have it already
2. Open HACS in Home Assistant
3. Go to "Integrations" section
4. Click ... button on top right and in menu select "Custom repositories"
5. Add repository **https://github.com/igkovace/hep_mjerenje** and select category "Integration"
6. Search for "HEP ODS Mjerenje" and install it
7. Restart Home Assistant

## 2. Manual Installation

Install it as you would do with any Home Assistant custom component:

1. Download the [zip](https://github.com/igkovace/hep-ods-mjerenje/archive/refs/heads/master.zip) and extract it
2. Copy the `hep_mjerenje` directory within the `custom_components` directory of your Home Assistant installation. The `custom_components` directory resides within the Home Assistant configuration directory.

**Note**: If the custom_components directory does not exist, it needs to be created.

After a correct installation, the configuration directory should look like the following:
```text
└── ...
└── custom_components
    └── hep_mjerenje
        └── translations/ 
        └── __init__.py
        └── api.py
        └── config_flow.py
        └── const.py
        └── coordinator.py
        └── exporter.py
        └── manifest.json
        └── sensor.py
        └── services.yaml
```

3. Restart Home Assistant.

# Configuration
1. From the Home Assistant web panel, navigate to **Settings** → **Devices & Services** → **Integrations**
2. Click the `+ Add Integration` button in the bottom right corner
3. Search for **HEP ODS Mjerenje** and select it
4. Enter your HEP ODS Mjerenje account **Username**, **Password**, **OIB**, **OMM**, then click Submit
5. *(Optional)* After configuration, you can change settings by clicking **Configure** on the integration

# Sensors
- **Total** (lifetime), **Year** (YTD), **This Month**, **Previous Month**, **Yesterday**, Diagnostics
## Entities
- `sensor.hep_consumption_total_kwh` (total_increasing)
- `sensor.hep_export_total_kwh` (total_increasing)
- `sensor.hep_consumption_this_month`
- `sensor.hep_export_this_month`
- `sensor.hep_consumption_today`
- `sensor.hep_export_today`

## Service
- `hep_mjerenje.import_history` (months, optional `force`)
- `hep_mjerenje.import_years` (years, optional `force`)
- `hep_mjerenje.reset_totals`
- `hep_mjerenje.clear_import_cache`

Backfill totals with a list of months, e.g.:
```
service: hep_mjerenje.import_history
data:
  months: ["09.2025, "10.2025", "11.2025"]
```

## Options (key ones)
- Backfill N months
- Reset totals on first install
- **Sync lifetime total to YTD** (new in v0.2.7)
- Parser indices, formats; value unit toggle; Influx export toggles and settings

## Notes
- The integration uses the portal endpoints observed in community scripts and may break if HEP changes them. Handle with care

## Debug Logging
To enable debug logging, add this to your configuration.yaml:
```
logger:
  default: warning
  logs:
    custom_components.hep_mjerenje: debug
    custom_components.hep_mjerenje.api: debug
    custom_components.hep_mjerenje.coordinator: debug
```

## Issues
To be concluded

## Changelog
### v0.2.7
- **Feature**: Added option **`sync_total_to_ytd`** (default ON). Coordinator ensures lifetime totals are **never smaller than YTD** by bumping them up when needed.
- **Stability**: Manifest version is PEP 440 compliant.

### v0.2.6
- Repacked all modules with full content (no placeholders), including 0.2.6 features.
- **Dedup**: Tracks imported months and skips duplicates automatically; new `clear_import_cache` and `force` flags.

### v0.2.5
- Added `import_years` service.

### v0.2.4
- Setup-order fix: reset/backfill before first refresh.
- **Total=lifetime**, **Year=YTD**; added `reset_on_install` option.

### v0.2.3
- **Fix**: Persistent totals file now namespaced per config entry (`OIB_OMM`) to prevent inflated totals after reinstall.
- **Feature**: Added `reset_totals` service to clear persistent totals.
- **UX**: `Backfill N months` moved to the initial setup form (login screen) for better user control.
- **i18n**: Added translations folder with English (`en.json`) and Croatian (`hr.json`).
- **Docs**: Restored README with version changes.
  
### v0.2.2
- **Fix**: Config flow handler loads reliably via lazy imports (prevents `Invalid handler specified` error).
- **Fix**: Exporter newline literal corrected; InfluxDB line protocol payload valid.
- **Fix**: `manifest.json` converted to valid JSON; version bumped.
- **Improve**: Sensors use OMM in `unique_id` to avoid collisions.

### v0.2.1
#### Hotfixes
- **Fix ImportError/SyntaxError in exporter.py**: safe quoting and using HA aiohttp session to avoid event loop warnings.
- Influx exporter now uses HA session (`aiohttp_client`) and avoids creating a new client.
#### Still includes v0.2.0 features
- Robust parser with auto-fallback, diagnostics, persistent totals, auto-backfill, optional Influx export.

### v0.2.0
#### Fixes
- **Month/Previous Month empty**: parser now **falls back to auto-detect columns** if provided indices yield 0 rows (header lookup for `Datum`, `Vrijeme`, `…energija`/`…snaga`, and a numeric heuristic that avoids `Status`). `diag_fallback_used` attribute shows when fallback triggered.
- Diagnostics expanded: `diag_current_month_rows`, `diag_prev_month_rows`, `diag_skipped_months`.
#### New
- **Persistent totals** using HA `Store` — `Consumption Total` and `Export Total` **keep growing across restarts and rollovers**. On first run (no store) totals initialize from **YTD**; auto-backfill then adds historical months.
- **Auto-backfill** (first setup): imports last **N** complete months (default 12), skipping months the portal doesn’t have yet (404-safe).
- **InfluxDB v2 exporter** (optional): push **15-min**, **daily**, and **monthly** series to Influx for Grafana. Configure in Options (`influx_enabled`, `influx_url`, `influx_token`, `influx_org`, `influx_bucket`).
#### Defaults (XLS layout)
- `date_col=1`, `time_col=2`, `kw_col=7`, `date_format=%d.%m.%Y`, `time_format=%H:%M:%S`, `value_is_energy=true`.

### v0.1.10
#### Fixes
- **Graceful 404 handling**: if a month endpoint returns **404 Not Found**, the integration **skips that month** and continues. This applies to:
- Current/previous month
- **YTD** aggregation
- **Auto-backfill** and manual `import_history`
- Diagnostics attribute **`diag_skipped_months`** lists skipped months (comma-separated) for visibility.
#### Behavior (kept from v0.1.9)
- Daily = **Yesterday** (naming + calculation).
- Sensor names simplified (no "HEP" prefix).
- Defaults for HEP XLS (`date_col=1`, `time_col=2`, `kw_col=7`, `value_is_energy=true`).
- Auto-backfill last **N** months on first setup (default 12).

### v0.1.9
#### What’s new
- **Sensor names simplified** (no "HEP" prefix) and **daily sensors explicitly show *Yesterday***.
- New sensors: **Consumption/Export Previous Month**, **Consumption/Export Year (YTD)**.
- Defaults pre-set for HEP XLS: `date_col=1`, `time_col=2`, `kw_col=7`, `value_is_energy=True`, `date_format=%d.%m.%Y`, `time_format=%H:%M:%S`.
- **Auto-backfill**: on first setup, automatically imports the last **N** complete months (default 12). You can change N in Options.
#### Entities
- Consumption Total (total_increasing)
- Export Total (total_increasing)
- Consumption This Month, Export This Month
- Consumption Yesterday, Export Yesterday
- Consumption Previous Month, Export Previous Month
- Consumption Year, Export Year
- Diagnostics (rows parsed and helper attributes)

### v0.1.8
#### Changes
- **Today = Yesterday** option (enabled by default): daily sensors show yesterday because the HEP portal publishes a day's curve only after the day closes.
- **Robust parsing** for Date+Time + value column selection; avoids picking the last "Status" column; adds preferred energy when two numeric columns exist.
- Options UI extended.

### v0.1.7
#### New
- Supports **separate Date + Time columns** (e.g., `Datum` and `Vrijeme`) and combines them for timestamps.
- Option to treat selected value column as **already energy (kWh)** so no kW→kWh conversion is applied.
#### Options
- `date_column_index` (default -1 = not used)
- `time_column_index` (default 0)
- `kw_column_index` (default -1 = last numeric column)
- `date_format` (default `%d.%m.%Y`)
- `time_format` (default `%H:%M:%S`)
- `value_is_energy` (default false)

Device hierarchy retained: Parent **HEP ODS Account** → Child **HEP <OMM>** with entities.

### v0.1.6
#### New: Parser Options & Diagnostics
- Set **Time column index**, **kW column index**, and **Time format** in the integration **Options**.
- New `sensor.hep_diagnostics` shows parsed row count and last timestamps.
#### Device hierarchy
- Parent device: **HEP ODS Account**
- Child device: **HEP <OMM>** with energy entities

### v0.1.5
#### Now with **device hierarchy**:
- Parent device: **HEP ODS Account**
- Child device per OMM: **HEP <OMM>** with all 6 energy entities

### v0.1.4
- Minor fixes

### v0.1.3
- Minor fixes

### v0.1.2
- Minor fixes

### v0.1.1
- First initial release

## License
This project is licensed under the MIT License.
