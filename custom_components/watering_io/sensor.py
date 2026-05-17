from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SIGNAL_UPDATE, WateringIoCoordinator
from .entity import WateringEntity, WateringPlanterEntity
from .helpers import (
    coerce_numeric,
    extract_planter_id,
    extract_sensor_id,
    total_water_ml,
)

SYSTEM_FIELDS = [
    "wifiRssi",
    "busCurrent",
    "uptime",
    "firmwareVersion",
    "buildGit",
    "buildCommit",
    "buildDirty",
    "buildTimeUtc",
]
PLANTER_DOSING_FIELDS = [
    "total_dosing_s",
    "total_water_ml",
]
PLANTER_FIELDS = [
    "moisture",
    "target_moisture",
    "sensor_modbus_id",
    "valve_route",
    "next_dose_s",
    *PLANTER_DOSING_FIELDS,
]
SENSOR_FIELDS = ["moisture", "temperature", "last_seen_s", "missedScans"]
PERCENTAGE_FIELDS = {"moisture", "target_moisture"}
SIGNAL_STRENGTH_FIELDS = {"wifiRssi"}
DURATION_FIELDS = {"total_dosing_s", "next_dose_s"}
TOTAL_INCREASING_FIELDS = {"total_dosing_s", "total_water_ml"}


def _status_value(data: dict, field: str, coordinator: WateringIoCoordinator | None = None):
    value = data.get(field)
    if field in PERCENTAGE_FIELDS or field in SIGNAL_STRENGTH_FIELDS:
        return coerce_numeric(value)
    if field == "total_dosing_s":
        return coerce_numeric(data.get("total_dosing_s"))
    if field == "next_dose_s":
        return coerce_numeric(data.get("next_dose_in_s"))
    if field == "total_water_ml" and coordinator is not None:
        return total_water_ml(data.get("total_dosing_s"), coordinator.pump_1_flow_ml_per_s)
    return value


def _set_field_metadata(entity: SensorEntity, field: str) -> None:
    if field in PERCENTAGE_FIELDS:
        entity._attr_device_class = SensorDeviceClass.MOISTURE
        entity._attr_native_unit_of_measurement = PERCENTAGE
        entity._attr_state_class = SensorStateClass.MEASUREMENT
    elif field in SIGNAL_STRENGTH_FIELDS:
        entity._attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
        entity._attr_native_unit_of_measurement = "dBm"
        entity._attr_state_class = SensorStateClass.MEASUREMENT
    elif field in DURATION_FIELDS:
        duration_device_class = getattr(SensorDeviceClass, "DURATION", None)
        if duration_device_class is not None:
            entity._attr_device_class = duration_device_class
        entity._attr_native_unit_of_measurement = UnitOfTime.SECONDS
        if field in TOTAL_INCREASING_FIELDS:
            entity._attr_state_class = SensorStateClass.TOTAL_INCREASING
    elif field == "total_water_ml":
        # Home Assistant's water device class does not accept mL; volume does.
        volume_device_class = getattr(SensorDeviceClass, "VOLUME", None)
        if volume_device_class is not None:
            entity._attr_device_class = volume_device_class
        entity._attr_native_unit_of_measurement = "mL"
        entity._attr_state_class = SensorStateClass.TOTAL_INCREASING


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: WateringIoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WateringSystemSensor(coordinator, f) for f in SYSTEM_FIELDS])

    added_planters: set[str] = set()
    added_sensors: set[str] = set()

    @callback
    def add_dynamic() -> None:
        new_entities = []
        for planter in coordinator.state.schema.get("entities", {}).get("planters", []):
            planter_id = extract_planter_id(planter)
            if not planter_id or planter_id in added_planters or coordinator.planter_unique_id(planter_id) is None:
                continue
            added_planters.add(planter_id)
            for field in PLANTER_FIELDS:
                new_entities.append(WateringPlanterSensor(coordinator, planter_id, field))

        for sensor in coordinator.state.schema.get("entities", {}).get("sensors", []):
            sensor_id = extract_sensor_id(sensor)
            if not sensor_id or sensor_id in added_sensors:
                continue
            added_sensors.add(sensor_id)
            for field in SENSOR_FIELDS:
                new_entities.append(WateringDynamicSensor(coordinator, sensor_id, field))

        for planter_id in coordinator.state.planter_status:
            if planter_id in added_planters or coordinator.planter_unique_id(planter_id) is None:
                continue
            added_planters.add(planter_id)
            for field in PLANTER_FIELDS:
                new_entities.append(WateringPlanterSensor(coordinator, planter_id, field))

        for sensor_id in coordinator.state.sensor_status:
            if sensor_id in added_sensors:
                continue
            added_sensors.add(sensor_id)
            for field in SENSOR_FIELDS:
                new_entities.append(WateringDynamicSensor(coordinator, sensor_id, field))

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_UPDATE, add_dynamic))
    add_dynamic()


class WateringSystemSensor(WateringEntity, SensorEntity):
    def __init__(self, coordinator: WateringIoCoordinator, field: str) -> None:
        super().__init__(coordinator)
        self.field = field
        self._attr_name = field
        self._attr_unique_id = f"{coordinator.device_id}_system_{field}"
        _set_field_metadata(self, field)

    @property
    def native_value(self):
        return _status_value(self.coordinator.state.system_status, self.field, self.coordinator)


class WateringPlanterSensor(WateringPlanterEntity, SensorEntity):
    def __init__(self, coordinator: WateringIoCoordinator, planter_id: str, field: str) -> None:
        super().__init__(coordinator, planter_id)
        self.field = field
        self._attr_name = f"Planter {planter_id} {field}"
        self._attr_unique_id = f"{self.planter_unique_id}_{field}"
        _set_field_metadata(self, field)

    @property
    def native_value(self):
        return _status_value(self.coordinator.state.planter_status.get(self.planter_id, {}), self.field, self.coordinator)


class WateringDynamicSensor(WateringEntity, SensorEntity):
    def __init__(self, coordinator: WateringIoCoordinator, sensor_id: str, field: str) -> None:
        super().__init__(coordinator)
        self.sensor_id = sensor_id
        self.field = field
        self._attr_name = f"Sensor {sensor_id} {field}"
        self._attr_unique_id = f"{coordinator.device_id}_sensor_{sensor_id}_{field}"
        _set_field_metadata(self, field)

    @property
    def native_value(self):
        return _status_value(self.coordinator.state.sensor_status.get(self.sensor_id, {}), self.field, self.coordinator)
