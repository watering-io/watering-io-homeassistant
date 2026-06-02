from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SIGNAL_UPDATE, WateringIoCoordinator
from .entity import WateringEntity, WateringPlanterEntity
from .helpers import coerce_bool, extract_planter_id, extract_sensor_id, nested_value

SCHEDULE_BINARY_FIELDS = [
    ("schedule_enabled", "Schedule enabled", ("enabled",)),
    ("schedule_auto_moisture_allowed", "Schedule auto moisture allowed", ("auto_moisture_allowed",)),
    ("schedule_time_synced", "Schedule time synced", ("time_synced",)),
]


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
                    PumpBinarySensor(coordinator, "pump_a", "pump_a"),
                    PumpBinarySensor(coordinator, "pump_b", "pump_b"),
                    PumpBinarySensor(coordinator, "any_on", "pump_any"),
                    *[
                        ScheduleBinarySensor(coordinator, unique_suffix, name, path)
                        for unique_suffix, name, path in SCHEDULE_BINARY_FIELDS
                    ],
                ]
            )
            static_added = True

        for planter in coordinator.state.schema.get("entities", {}).get("planters", []):
            planter_id = extract_planter_id(planter)
            if not planter_id or planter_id in added_planters or coordinator.planter_unique_id(planter_id) is None:
                continue
            added_planters.add(planter_id)
            new_entities.extend(
                [
                    PlanterBinarySensor(coordinator, planter_id, "watering"),
                    PlanterBinarySensor(coordinator, planter_id, "online"),
                ]
            )

        for sensor in coordinator.state.schema.get("entities", {}).get("sensors", []):
            sensor_id = extract_sensor_id(sensor)
            if not sensor_id or sensor_id in added_sensors:
                continue
            added_sensors.add(sensor_id)
            new_entities.append(SensorOnlineBinarySensor(coordinator, sensor_id))

        for planter_id in coordinator.state.planter_status:
            if planter_id in added_planters or coordinator.planter_unique_id(planter_id) is None:
                continue
            added_planters.add(planter_id)
            new_entities.extend(
                [
                    PlanterBinarySensor(coordinator, planter_id, "watering"),
                    PlanterBinarySensor(coordinator, planter_id, "online"),
                ]
            )

        for sensor_id in coordinator.state.sensor_status:
            if sensor_id in added_sensors:
                continue
            added_sensors.add(sensor_id)
            new_entities.append(SensorOnlineBinarySensor(coordinator, sensor_id))

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_UPDATE, add_dynamic))
    add_dynamic()


class PumpBinarySensor(WateringEntity, BinarySensorEntity):
    def __init__(
        self,
        coordinator: WateringIoCoordinator,
        field: str,
        suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self.field = field
        self._attr_name = suffix
        self._attr_unique_id = f"{coordinator.stable_unique_prefix}_{suffix}"

    @property
    def is_on(self):
        return bool(self.coordinator.state.pumps_status.get(self.field, False))


class ScheduleBinarySensor(WateringEntity, BinarySensorEntity):
    def __init__(
        self,
        coordinator: WateringIoCoordinator,
        unique_suffix: str,
        name: str,
        path: tuple[str, ...],
    ) -> None:
        super().__init__(coordinator)
        self.path = path
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.stable_unique_prefix}_{unique_suffix}"

    @property
    def is_on(self):
        return coerce_bool(nested_value(self.coordinator.state.schedule_status, self.path))


class PlanterBinarySensor(WateringPlanterEntity, BinarySensorEntity):
    def __init__(self, coordinator: WateringIoCoordinator, planter_id: str, field: str) -> None:
        super().__init__(coordinator, planter_id)
        self.field = field
        self._attr_name = f"Planter {planter_id} {field}"
        self._attr_unique_id = f"{self.planter_unique_id}_{field}"

    @property
    def is_on(self):
        return bool(self.coordinator.state.planter_status.get(self.planter_id, {}).get(self.field, False))


class SensorOnlineBinarySensor(WateringEntity, BinarySensorEntity):
    def __init__(self, coordinator: WateringIoCoordinator, sensor_id: str) -> None:
        super().__init__(coordinator)
        self.sensor_id = sensor_id
        self._attr_name = f"Sensor {sensor_id} online"
        self._attr_unique_id = coordinator.sensor_unique_id(sensor_id, "online")

    @property
    def is_on(self):
        return bool(self.coordinator.state.sensor_status.get(self.sensor_id, {}).get("online", False))
