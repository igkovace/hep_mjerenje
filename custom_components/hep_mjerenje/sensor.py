
from __future__ import annotations
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import UnitOfEnergy
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    DOMAIN,
    KEY_CONS_TOTAL, KEY_EXP_TOTAL,
    KEY_CONS_MONTH, KEY_EXP_MONTH,
    KEY_CONS_YESTERDAY, KEY_EXP_YESTERDAY,
    KEY_CONS_PREV_MONTH, KEY_EXP_PREV_MONTH,
    KEY_CONS_YEAR, KEY_EXP_YEAR,
    CONF_OMM,
)

ENERGY_SPECS = [
    ("Consumption Total", KEY_CONS_TOTAL, "total_increasing"),
    ("Export Total", KEY_EXP_TOTAL, "total_increasing"),
    ("Consumption This Month", KEY_CONS_MONTH, "total"),
    ("Export This Month", KEY_EXP_MONTH, "total"),
    ("Consumption Yesterday", KEY_CONS_YESTERDAY, "total"),
    ("Export Yesterday", KEY_EXP_YESTERDAY, "total"),
    ("Consumption Previous Month", KEY_CONS_PREV_MONTH, "total"),
    ("Export Previous Month", KEY_EXP_PREV_MONTH, "total"),
    ("Consumption Year", KEY_CONS_YEAR, "total"),
    ("Export Year", KEY_EXP_YEAR, "total"),
]

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback):
    coordinator = hass.data[DOMAIN]["coordinator"]
    omm = entry.data[CONF_OMM]

    parent_ident = (DOMAIN, "hep_account")
    child_device_info = DeviceInfo(
        identifiers={(DOMAIN, omm)},
        name=f"HEP {omm}",
        manufacturer="HEP ODS",
        model="Smart Meter",
        via_device=parent_ident,
    )

    energy_entities = [HepEnergySensor(coordinator, name, key, state_class, child_device_info, omm) for (name, key, state_class) in ENERGY_SPECS]
    diag_entity = HepDiagSensor(coordinator, "Diagnostics", child_device_info)
    async_add_entities(energy_entities + [diag_entity])

class HepEnergySensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, name, key, state_class, device_info: DeviceInfo, omm: str):
        super().__init__(coordinator)
        self._attr_name = name
        self._key = key
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = state_class
        self._attr_unique_id = f"hep_mjerenje_{omm}_{key}"
        self._attr_device_info = device_info

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return data.get(self._key)

class HepDiagSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, name, device_info: DeviceInfo):
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_unique_id = "hep_mjerenje_diag"
        self._attr_device_info = device_info
        self._attr_icon = "mdi:information-outline"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return data.get('diag_rows_total')

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        return {k: v for k, v in data.items() if k.startswith('diag_')}
