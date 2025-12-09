
from __future__ import annotations
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import ENERGY_KILO_WATT_HOUR
from .const import (
    DOMAIN,
    KEY_CONS_TOTAL, KEY_EXP_TOTAL,
    KEY_CONS_MONTH, KEY_EXP_MONTH,
    KEY_CONS_TODAY, KEY_EXP_TODAY,
)

SENSOR_SPECS = [
    ("HEP Consumption Total", KEY_CONS_TOTAL, "total_increasing"),
    ("HEP Export Total", KEY_EXP_TOTAL, "total_increasing"),
    ("HEP Consumption This Month", KEY_CONS_MONTH, "measurement"),
    ("HEP Export This Month", KEY_EXP_MONTH, "measurement"),
    ("HEP Consumption Today", KEY_CONS_TODAY, "measurement"),
    ("HEP Export Today", KEY_EXP_TODAY, "measurement"),
]

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback):
    coordinator = hass.data[DOMAIN]["coordinator"]
    entities = [HepEnergySensor(coordinator, name, key, state_class) for (name, key, state_class) in SENSOR_SPECS]
    async_add_entities(entities)

class HepEnergySensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, name, key, state_class):
        super().__init__(coordinator)
        self._attr_name = name
        self._key = key
        self._attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
        self._attr_device_class = "energy"
        self._attr_state_class = state_class
        self._attr_unique_id = f"hep_mjerenje_{key}"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return data.get(self._key)
