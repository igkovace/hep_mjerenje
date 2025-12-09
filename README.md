![GitHub](https://img.shields.io/badge/GitHub-100000?logo=github&logoColor=white)
![Python](https://img.shields.io/badge/Python-14354C?style=flat&logo=python&logoColor=white)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/igkovace/hep-ods-mjerenje)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

# HEP ODS Mjerenje – Home Assistant Custom Integration

## About
This integration pulls [HEP ODS Mjerenje](https://mjerenje.hep.hr/)'s API 15‑minute power curves from the HEP ODS "Mjerenje" portal and exposes energy sensors suitable for Home Assistant Energy Dashboard.

## Installation
## 1. Easy Mode (HACS)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

1. Open HACS and search for `HEP ODS Mjerenje`
1. Click `Download`
1. Continue to [Configuration](#configuration)

## 2. Manual Installation

Install it as you would do with any Home Assistant custom component:

1. Download the `custom_components` folder from this repository.
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

# Usage
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
- The integration uses the portal endpoints observed in community scripts and may break if HEP changes them. Handle with care


## Debug Logging
To enable debug logging, add this to your configuration.yaml:

logger:
  default: warning
  logs:
    custom_components.hep_mjerenje: debug
    custom_components.hep_mjerenje.api: debug
    custom_components.hep_mjerenje.coordinator: debug

## License
This project is licensed under the MIT License.
