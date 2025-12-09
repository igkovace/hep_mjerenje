
# HEP ODS Mjerenje – Home Assistant Custom Integration (v0.1.1)

This integration pulls 15‑minute power curves from the HEP ODS "Mjerenje" portal and exposes energy sensors suitable for Home Assistant Energy Dashboard.

## Install
1. Copy `custom_components/hep_mjerenje/` into your Home Assistant `config/custom_components/` folder.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration** and search for **HEP ODS Mjerenje**.
4. Enter **Username**, **Password**, **OIB**, **OMM**.

## Entities
- `sensor.hep_consumption_total_kwh` (total_increasing)
- `sensor.hep_export_total_kwh` (total_increasing)
- `sensor.hep_consumption_this_month`
- `sensor.hep_export_this_month`
- `sensor.hep_consumption_today`
- `sensor.hep_export_today`

## Service: `hep_mjerenje.import_history`
Backfill totals with a list of months, e.g.:
```
service: hep_mjerenje.import_history
data:
  months: ["03.2023", "04.2023", "05.2023"]
```

## Notes
- Power (kW) values are converted to energy (kWh) by dividing by 4 for each 15‑minute interval.
- The integration uses the portal endpoints observed in community scripts and may break if HEP changes them. Handle with care.
