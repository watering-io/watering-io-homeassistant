from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SIGNAL_UPDATE, WateringIoCoordinator
from .entity import WateringEntity, WateringPlanterEntity
from .helpers import extract_planter_id, extract_sensor_id


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: WateringIoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            PumpBinarySensor(coordinator, "pumpA", "pump_a"),
            PumpBinarySensor(coordinator, "pumpB", "pump_b"),
            PumpBinarySensor(coordinator, "anyOn", "pump_any"),
        ]
    )

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
    def __init__(self, coordinator: WateringIoCoordinator, field: str, suffix: str) -> None:
        super().__init__(coordinator)
        self.field = field
        self._attr_name = suffix
        self._attr_unique_id = f"{coordinator.device_id}_{suffix}"

    @property
    def is_on(self):
        return bool(self.coordinator.state.pumps_status.get(self.field, False))


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
        self._attr_unique_id = f"{coordinator.device_id}_sensor_{sensor_id}_online"

    @property
    def is_on(self):
        return bool(self.coordinator.state.sensor_status.get(self.sensor_id, {}).get("online", False))
