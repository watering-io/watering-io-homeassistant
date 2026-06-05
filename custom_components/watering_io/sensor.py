from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SIGNAL_UPDATE, WateringIoCoordinator
from .entity import WateringEntity, WateringPlanterEntity
from .helpers import (
    coerce_numeric,
    daily_water_history,
    extract_planter_id,
    extract_sensor_id,
    nested_value,
    today_water_ml,
    total_water_ml,
)

SYSTEM_FIELDS = [
    "uptime_s",
    "wifi_rssi",
    "bus_current",
    "input_current",
    "firmware_version",
    "build_git",
    "build_commit",
    "build_dirty",
    "build_time_utc",
]
PLANTER_DOSING_FIELDS = [
    "total_dosing_s",
    "total_water_ml",
    "daily_water",
]
SCHEDULE_SENSOR_FIELDS = [
    ("schedule_phase", "Schedule phase", ("phase",)),
    ("schedule_local_date", "Schedule local date", ("local_date",)),
    ("schedule_night_start", "Schedule night start", ("schedule", "night_start")),
    ("schedule_drydown_start", "Schedule drydown start", ("schedule", "drydown_start")),
    ("schedule_fertilizer_start", "Schedule fertilizer start", ("schedule", "fertilizer_start")),
    ("schedule_normal_start", "Schedule normal start", ("schedule", "normal_start")),
    ("fertilizer_state", "Fertilizer state", ("fertilizer", "state")),
    ("fertilizer_last_run_date", "Fertilizer last run date", ("fertilizer", "last_run_date")),
    ("fertilizer_current_planter_id", "Fertilizer current planter ID", ("fertilizer", "current_planter_id")),
    ("fertilizer_completed_count", "Fertilizer completed count", ("fertilizer", "completed_count")),
    ("fertilizer_skipped_count", "Fertilizer skipped count", ("fertilizer", "skipped_count")),
    ("fertilizer_last_error", "Fertilizer last error", ("fertilizer", "last_error")),
]
PLANTER_FIELDS = [
    "moisture",
    "target_moisture",
    "sensor_modbus_id",
    "valve_route",
    "next_dose_s",
    *PLANTER_DOSING_FIELDS,
]
SENSOR_FIELDS = ["moisture", "temperature", "last_seen_s", "missed_scans"]
PERCENTAGE_FIELDS = {"moisture", "target_moisture"}
SIGNAL_STRENGTH_FIELDS = {"wifi_rssi"}
TEMPERATURE_FIELDS = {"temperature"}
CURRENT_FIELDS = {"bus_current", "input_current"}
DURATION_FIELDS = {"uptime_s", "total_dosing_s", "next_dose_s"}
TOTAL_INCREASING_FIELDS = {"total_dosing_s", "total_water_ml"}
VOLUME_FIELDS = {"total_water_ml", "daily_water"}
NUMERIC_FIELDS = {"last_seen_s", "missed_scans", *CURRENT_FIELDS, *DURATION_FIELDS}
SCHEDULE_NUMERIC_FIELDS = {
    "fertilizer_current_planter_id",
    "fertilizer_completed_count",
    "fertilizer_skipped_count",
}

FIELD_ALIASES = {
    "uptime_s": ("uptime_s", "uptime"),
    "wifi_rssi": ("wifi_rssi", "wifiRssi"),
    "bus_current": ("bus_current", "busCurrent"),
    "input_current": ("input_current", "inputCurrent"),
    "firmware_version": ("firmware_version", "firmwareVersion"),
    "build_git": ("build_git", "buildGit"),
    "build_commit": ("build_commit", "buildCommit"),
    "build_dirty": ("build_dirty", "buildDirty"),
    "build_time_utc": ("build_time_utc", "buildTimeUtc"),
    "missed_scans": ("missed_scans", "missedScans"),
    "next_dose_s": ("next_dose_in_s", "next_dose_s", "nextDoseInS"),
}


def _field_value(data: dict, field: str):
    for key in FIELD_ALIASES.get(field, (field,)):
        if key in data:
            return data.get(key)
    return None


def _status_value(data: dict, field: str, coordinator: WateringIoCoordinator | None = None):
    value = _field_value(data, field)
    if field == "total_dosing_s":
        return coerce_numeric(value)
    if field == "next_dose_s":
        return coerce_numeric(value)
    if field in PERCENTAGE_FIELDS or field in SIGNAL_STRENGTH_FIELDS or field in TEMPERATURE_FIELDS:
        return coerce_numeric(value)
    if field in NUMERIC_FIELDS:
        return coerce_numeric(value)
    if field == "total_water_ml" and coordinator is not None:
        return total_water_ml(data.get("total_dosing_s"), coordinator.pump_1_flow_ml_per_s)
    if field == "daily_water" and coordinator is not None:
        return today_water_ml(data, coordinator.pump_1_flow_ml_per_s)
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
    elif field in TEMPERATURE_FIELDS:
        entity._attr_device_class = SensorDeviceClass.TEMPERATURE
        entity._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        entity._attr_state_class = SensorStateClass.MEASUREMENT
    elif field in CURRENT_FIELDS:
        entity._attr_device_class = SensorDeviceClass.CURRENT
        entity._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        entity._attr_state_class = SensorStateClass.MEASUREMENT
    elif field in DURATION_FIELDS:
        duration_device_class = getattr(SensorDeviceClass, "DURATION", None)
        if duration_device_class is not None:
            entity._attr_device_class = duration_device_class
        entity._attr_native_unit_of_measurement = UnitOfTime.SECONDS
        if field in TOTAL_INCREASING_FIELDS:
            entity._attr_state_class = SensorStateClass.TOTAL_INCREASING
    elif field in VOLUME_FIELDS:
        # Home Assistant's water device class does not accept mL; volume does.
        volume_device_class = getattr(SensorDeviceClass, "VOLUME", None)
        if volume_device_class is not None:
            entity._attr_device_class = volume_device_class
        entity._attr_native_unit_of_measurement = "mL"
        entity._attr_state_class = (
            SensorStateClass.TOTAL_INCREASING
            if field in TOTAL_INCREASING_FIELDS
            else SensorStateClass.MEASUREMENT
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: WateringIoCoordinator = hass.data[DOMAIN][entry.entry_id]
    static_added = False
    added_planters: set[str] = set()
    added_sensors: set[str] = set()

    @callback
    def add_dynamic() -> None:
        nonlocal static_added
        if not coordinator.hub_id_available:
            return

        new_entities = []
        if not static_added:
            new_entities.extend(
                [
                    *[WateringSystemSensor(coordinator, f) for f in SYSTEM_FIELDS],
                    *[
                        WateringScheduleSensor(coordinator, unique_suffix, name, path)
                        for unique_suffix, name, path in SCHEDULE_SENSOR_FIELDS
                    ],
                ]
            )
            static_added = True

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
        self._attr_unique_id = f"{coordinator.stable_unique_prefix}_system_{field}"
        _set_field_metadata(self, field)

    @property
    def native_value(self):
        return _status_value(self.coordinator.state.system_status, self.field, self.coordinator)


class WateringScheduleSensor(WateringEntity, SensorEntity):
    def __init__(
        self,
        coordinator: WateringIoCoordinator,
        unique_suffix: str,
        name: str,
        path: tuple[str, ...],
    ) -> None:
        super().__init__(coordinator)
        self.unique_suffix = unique_suffix
        self.path = path
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.stable_unique_prefix}_{unique_suffix}"

    @property
    def native_value(self):
        value = nested_value(self.coordinator.state.schedule_status, self.path)
        if value is None and self.unique_suffix.startswith("fertilizer_"):
            value = nested_value(self.coordinator.state.fertilizer_status, self.path[1:])
        if self.unique_suffix in SCHEDULE_NUMERIC_FIELDS:
            return coerce_numeric(value)
        return value


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

    @property
    def extra_state_attributes(self):
        if self.field != "daily_water":
            return None
        history = daily_water_history(
            self.coordinator.state.planter_status.get(self.planter_id, {}),
            self.coordinator.pump_1_flow_ml_per_s,
        )
        return {"daily_water": history}


class WateringDynamicSensor(WateringEntity, SensorEntity):
    def __init__(self, coordinator: WateringIoCoordinator, sensor_id: str, field: str) -> None:
        super().__init__(coordinator)
        self.sensor_id = sensor_id
        self.field = field
        self._attr_name = f"Sensor {sensor_id} {field}"
        self._attr_unique_id = coordinator.sensor_unique_id(sensor_id, field)
        _set_field_metadata(self, field)

    @property
    def native_value(self):
        return _status_value(self.coordinator.state.sensor_status.get(self.sensor_id, {}), self.field, self.coordinator)
