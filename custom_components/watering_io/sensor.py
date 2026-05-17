from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SIGNAL_UPDATE, WateringIoCoordinator
from .entity import WateringEntity, WateringPlanterEntity
from .helpers import extract_planter_id, extract_sensor_id

SYSTEM_FIELDS = ["wifiRssi", "busCurrent", "uptime", "firmwareVersion", "buildGit", "buildCommit", "buildDirty", "buildTimeUtc"]
PLANTER_FIELDS = ["moisture", "target", "nextDoseInMs", "state", "valveMask", "dose_ms"]
SENSOR_FIELDS = ["moisture", "temperature", "lastSeenMs", "missedScans"]
PERCENTAGE_FIELDS = {"moisture", "target"}
SIGNAL_STRENGTH_FIELDS = {"wifiRssi"}


def _coerce_numeric(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
        return int(number) if number.is_integer() else number
    return None


def _status_value(data: dict, field: str):
    value = data.get(field)
    if field in PERCENTAGE_FIELDS or field in SIGNAL_STRENGTH_FIELDS:
        return _coerce_numeric(value)
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
            if not planter_id or planter_id in added_planters:
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
            if planter_id in added_planters:
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
        return _status_value(self.coordinator.state.system_status, self.field)


class WateringPlanterSensor(WateringPlanterEntity, SensorEntity):
    def __init__(self, coordinator: WateringIoCoordinator, planter_id: str, field: str) -> None:
        super().__init__(coordinator, planter_id)
        self.field = field
        self._attr_name = f"Planter {planter_id} {field}"
        self._attr_unique_id = f"{coordinator.device_id}_planter_{planter_id}_{field}"
        _set_field_metadata(self, field)

    @property
    def native_value(self):
        return _status_value(self.coordinator.state.planter_status.get(self.planter_id, {}), self.field)


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
        return _status_value(self.coordinator.state.sensor_status.get(self.sensor_id, {}), self.field)
