from __future__ import annotations

DOMAIN = "hep_mjerenje"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_OIB = "oib"
CONF_OMM = "omm"

# Scan interval default
DEFAULT_SCAN_INTERVAL_MINUTES = 360  # 6 hours

# Services
SERVICE_IMPORT_HISTORY = "import_history"

# Fixed parser configuration (no longer exposed in Options)
FIXED_DATE_COL = 1
FIXED_TIME_COL = 2
FIXED_KW_COL   = 7
FIXED_DATE_FMT = "%d.%m.%Y"
FIXED_TIME_FMT = "%H:%M:%S"
FIXED_VALUE_IS_ENERGY = True  # Mjerenje portal values are kWh

# Backfill control
CONF_BACKFILL_N_MONTHS = "backfill_n_months"
CONF_BACKFILL_DONE = "backfill_done"
DEFAULT_BACKFILL_N_MONTHS = 12

# Lifecycle options
CONF_RESET_ON_INSTALL = "reset_on_install"
DEFAULT_RESET_ON_INSTALL = True
CONF_SYNC_TOTAL_TO_YTD = "sync_total_to_ytd"
DEFAULT_SYNC_TOTAL_TO_YTD = True

# Influx exporter options
CONF_EXPORTER_ENABLED = "influx_enabled"
CONF_INFLUX_URL = "influx_url"
CONF_INFLUX_TOKEN = "influx_token"
CONF_INFLUX_ORG = "influx_org"
CONF_INFLUX_BUCKET = "influx_bucket"
CONF_EXPORT_SERIES_15M = "export_series_15m"
CONF_EXPORT_SERIES_DAILY = "export_series_daily"
CONF_EXPORT_SERIES_MONTHLY = "export_series_monthly"
DEFAULT_EXPORTER_ENABLED = False
DEFAULT_EXPORT_SERIES_15M = True
DEFAULT_EXPORT_SERIES_DAILY = True
DEFAULT_EXPORT_SERIES_MONTHLY = True

# Advanced options
CONF_UPDATE_INTERVAL_MINUTES = "update_interval_minutes"
CONF_REQUEST_TIMEOUT = "request_timeout"
CONF_MAX_CONCURRENCY = "max_concurrency"
DEFAULT_UPDATE_INTERVAL_MINUTES = DEFAULT_SCAN_INTERVAL_MINUTES
DEFAULT_REQUEST_TIMEOUT = 30  # seconds
DEFAULT_MAX_CONCURRENCY = 2

# Sensor keys
KEY_CONS_TOTAL = "consumption_total_kwh"  # lifetime
KEY_EXP_TOTAL  = "export_total_kwh"       # lifetime
KEY_CONS_MONTH = "consumption_month_kwh"
KEY_EXP_MONTH  = "export_month_kwh"
KEY_CONS_YESTERDAY = "consumption_yesterday_kwh"
KEY_EXP_YESTERDAY  = "export_yesterday_kwh"
KEY_CONS_PREV_MONTH = "consumption_prev_month_kwh"
KEY_EXP_PREV_MONTH  = "export_prev_month_kwh"
KEY_CONS_YEAR = "consumption_year_kwh"    # YTD
KEY_EXP_YEAR  = "export_year_kwh"         # YTD

# Diagnostics keys
KEY_DIAG_ROWS = "diag_rows_total"
KEY_DIAG_LAST_TS_P = "diag_last_ts_p"
KEY_DIAG_LAST_TS_R = "diag_last_ts_r"
KEY_DIAG_SUM_P = "diag_sum_p_kwh"
KEY_DIAG_SUM_R = "diag_sum_r_kwh"
KEY_DIAG_SKIPPED_MONTHS = "diag_skipped_months"
KEY_DIAG_FALLBACK_USED = "diag_fallback_used"
KEY_DIAG_CUR_ROWS = "diag_current_month_rows"
KEY_DIAG_PREV_ROWS = "diag_prev_month_rows"

# Persistence keys
PERSIST_IMPORTED_MONTHS = "imported_months"
