from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SIGNAL_UPDATE, WateringIoCoordinator
from .entity import WateringPlanterEntity, WateringPumpEntity
from .helpers import (
    coerce_numeric,
    extract_planter_id,
    planter_config_set_payload,
    planter_config_update_source,
    pump_config_set_payload,
    pump_config_update_source,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: WateringIoCoordinator = hass.data[DOMAIN][entry.entry_id]
    pump_numbers_added = False
    added_planters: set[str] = set()

    @callback
    def add_dynamic() -> None:
        nonlocal pump_numbers_added
        new_entities = []
        if coordinator.hub_id_available and not pump_numbers_added:
            for pump_id in ("1", "2"):
                if coordinator.pump_unique_id(pump_id) is None:
                    continue
                new_entities.extend(
                    [
                        PumpLevelSensorIdNumber(coordinator, pump_id),
                        PumpLowLevelThresholdNumber(coordinator, pump_id),
                        PumpSetLevelNumber(coordinator, pump_id),
                        PumpMaxRelayOnTimeNumber(coordinator, pump_id),
                        PumpMaxDailyRefillOnTimeNumber(coordinator, pump_id),
                    ]
                )
            pump_numbers_added = True

        planter_ids = set(coordinator.state.planter_configs)
        for planter in coordinator.state.schema.get("entities", {}).get("planters", []):
            planter_id = extract_planter_id(planter)
            if planter_id:
                planter_ids.add(planter_id)
        planter_ids.update(coordinator.state.planter_status)

        for planter_id in sorted(planter_ids, key=lambda value: (0, int(value)) if value.isdigit() else (1, value)):
            if planter_id in added_planters or coordinator.planter_unique_id(planter_id) is None:
                continue
            added_planters.add(planter_id)
            new_entities.extend(
                [
                    PlanterTargetMoistureNumber(coordinator, planter_id),
                    PlanterFertilizerStepsNumber(coordinator, planter_id),
                    PlanterMaxDailyDosingNumber(coordinator, planter_id),
                ]
            )

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_UPDATE, add_dynamic))
    add_dynamic()
    if coordinator.hub_id_available:
        await coordinator.async_publish_planter_get()
        await coordinator.async_publish_pump_config_get()


def _update_source(coordinator: WateringIoCoordinator, planter_id: str) -> dict | None:
    return planter_config_update_source(
        coordinator.state.planter_configs.get(planter_id),
        coordinator.state.planter_status.get(planter_id),
    )


def _pump_update_source(coordinator: WateringIoCoordinator, pump_id: str) -> dict | None:
    return pump_config_update_source(
        coordinator.state.pump_configs.get(pump_id),
        coordinator.state.pumps_status.get(f"pump{pump_id}"),
    )


class PumpReservoirNumber(WateringPumpEntity, NumberEntity):
    config_key = ""

    def __init__(self, coordinator: WateringIoCoordinator, pump_id: str) -> None:
        super().__init__(coordinator, pump_id)

    @property
    def available(self) -> bool:
        return super().available and self._config_payload_available()

    @property
    def native_value(self) -> int | None:
        for source in (
            self.coordinator.state.pump_configs.get(self.pump_id, {}),
            self.coordinator.state.pumps_status.get(f"pump{self.pump_id}", {}),
        ):
            value = coerce_numeric(source.get(self.config_key))
            if value is not None:
                return int(value)
        return None

    async def async_set_native_value(self, value: float) -> None:
        config = _pump_update_source(self.coordinator, self.pump_id)
        if not config:
            raise HomeAssistantError(
                f"Pump {self.pump_id} reservoir config is not loaded; refresh pump config before editing"
            )

        kwargs = {self.config_key: int(value)}
        try:
            payload = pump_config_set_payload(config, **kwargs)
        except (TypeError, ValueError) as err:
            raise HomeAssistantError(f"Pump {self.pump_id} reservoir config is incomplete: {err}") from err

        await self.coordinator.async_publish_pump_config_set(**payload)
        await self.coordinator.async_publish_pump_config_get()

    def _config_payload_available(self) -> bool:
        config = _pump_update_source(self.coordinator, self.pump_id)
        if not config:
            return False
        try:
            pump_config_set_payload(config)
        except (TypeError, ValueError):
            return False
        return True


class PumpLevelSensorIdNumber(PumpReservoirNumber):
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 16
    _attr_native_step = 1
    config_key = "level_sensor_modbus_id"

    def __init__(self, coordinator: WateringIoCoordinator, pump_id: str) -> None:
        super().__init__(coordinator, pump_id)
        self._attr_name = "Level sensor Modbus ID"
        self._attr_unique_id = f"{self.pump_unique_id}_level_sensor_modbus_id_number"


class PumpLowLevelThresholdNumber(PumpReservoirNumber):
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    config_key = "low_level_threshold_percent"

    def __init__(self, coordinator: WateringIoCoordinator, pump_id: str) -> None:
        super().__init__(coordinator, pump_id)
        self._attr_name = "Low level threshold"
        self._attr_unique_id = f"{self.pump_unique_id}_low_level_threshold_percent_number"


class PumpSetLevelNumber(PumpReservoirNumber):
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    config_key = "set_level_percent"

    def __init__(self, coordinator: WateringIoCoordinator, pump_id: str) -> None:
        super().__init__(coordinator, pump_id)
        self._attr_name = "Set level"
        self._attr_unique_id = f"{self.pump_unique_id}_set_level_percent_number"


class PumpMaxRelayOnTimeNumber(PumpReservoirNumber):
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 65535
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    config_key = "max_relay_on_time_s"

    def __init__(self, coordinator: WateringIoCoordinator, pump_id: str) -> None:
        super().__init__(coordinator, pump_id)
        self._attr_name = "Max refill on time"
        self._attr_unique_id = f"{self.pump_unique_id}_max_relay_on_time_s_number"


class PumpMaxDailyRefillOnTimeNumber(PumpReservoirNumber):
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 86400
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    config_key = "max_daily_refill_on_time_s"

    def __init__(self, coordinator: WateringIoCoordinator, pump_id: str) -> None:
        super().__init__(coordinator, pump_id)
        self._attr_name = "Max daily refill on time"
        self._attr_unique_id = f"{self.pump_unique_id}_max_daily_refill_on_time_s_number"


class PlanterTargetMoistureNumber(WateringPlanterEntity, NumberEntity):
    _attr_device_class = NumberDeviceClass.MOISTURE
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: WateringIoCoordinator, planter_id: str) -> None:
        super().__init__(coordinator, planter_id)
        self._attr_name = "Target moisture"
        self._attr_unique_id = f"{self.planter_unique_id}_target_moisture_number"

    @property
    def available(self) -> bool:
        return super().available and self._config_payload_available()

    @property
    def native_value(self) -> float | int | None:
        planter_config = self.coordinator.state.planter_configs.get(self.planter_id, {})
        config_value = planter_config.get("target_moisture", planter_config.get("targetMoisture"))
        if config_value is not None:
            return coerce_numeric(config_value)
        return coerce_numeric(
            self.coordinator.state.planter_status.get(self.planter_id, {}).get("target_moisture")
        )

    async def async_set_native_value(self, value: float) -> None:
        config = _update_source(self.coordinator, self.planter_id)
        if not config:
            raise HomeAssistantError(
                f"Planter {self.planter_id} config is not loaded; refresh planter list before editing target moisture"
            )

        try:
            payload = planter_config_set_payload(config, value)
        except (TypeError, ValueError) as err:
            raise HomeAssistantError(f"Planter {self.planter_id} config is incomplete: {err}") from err

        await self.coordinator.async_publish_planter_set(**payload)
        await self.coordinator.async_publish_planter_get()

    def _config_payload_available(self) -> bool:
        config = _update_source(self.coordinator, self.planter_id)
        if not config:
            return False
        try:
            planter_config_set_payload(config, self.native_value or 0)
        except (TypeError, ValueError):
            return False
        return True


class PlanterFertilizerStepsNumber(WateringPlanterEntity, NumberEntity):
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 100000
    _attr_native_step = 1

    def __init__(self, coordinator: WateringIoCoordinator, planter_id: str) -> None:
        super().__init__(coordinator, planter_id)
        self._attr_name = "Fertilizer steps"
        self._attr_unique_id = f"{self.planter_unique_id}_fertilizer_steps_number"

    @property
    def available(self) -> bool:
        return super().available and self._config_payload_available()

    @property
    def native_value(self) -> int | None:
        planter_config = self.coordinator.state.planter_configs.get(self.planter_id, {})
        config_value = planter_config.get("fertilizer_steps", planter_config.get("fertilizerSteps"))
        if config_value is None:
            config_value = self.coordinator.state.planter_status.get(self.planter_id, {}).get("fertilizer_steps")
        value = coerce_numeric(config_value)
        if value is None:
            return None
        return int(value)

    async def async_set_native_value(self, value: float) -> None:
        config = _update_source(self.coordinator, self.planter_id)
        if not config:
            raise HomeAssistantError(
                f"Planter {self.planter_id} config is not loaded; refresh planter list before editing fertilizer steps"
            )

        try:
            payload = planter_config_set_payload(config, fertilizer_steps=int(value))
        except (TypeError, ValueError) as err:
            raise HomeAssistantError(f"Planter {self.planter_id} config is incomplete: {err}") from err

        await self.coordinator.async_publish_planter_set(**payload)
        await self.coordinator.async_publish_planter_get()

    def _config_payload_available(self) -> bool:
        config = _update_source(self.coordinator, self.planter_id)
        if not config:
            return False
        try:
            planter_config_set_payload(config, fertilizer_steps=self.native_value or 0)
        except (TypeError, ValueError):
            return False
        return True


class PlanterMaxDailyDosingNumber(WateringPlanterEntity, NumberEntity):
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 86400
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS

    def __init__(self, coordinator: WateringIoCoordinator, planter_id: str) -> None:
        super().__init__(coordinator, planter_id)
        self._attr_name = "Max daily dosing"
        self._attr_unique_id = f"{self.planter_unique_id}_max_daily_dosing_s_number"

    @property
    def available(self) -> bool:
        return super().available and self._config_payload_available()

    @property
    def native_value(self) -> int | None:
        planter_config = self.coordinator.state.planter_configs.get(self.planter_id, {})
        config_value = planter_config.get("max_daily_dosing_s", planter_config.get("maxDailyDosingS"))
        if config_value is None:
            config_value = self.coordinator.state.planter_status.get(self.planter_id, {}).get("max_daily_dosing_s")
        value = coerce_numeric(config_value)
        if value is None:
            return None
        return int(value)

    async def async_set_native_value(self, value: float) -> None:
        config = _update_source(self.coordinator, self.planter_id)
        if not config:
            raise HomeAssistantError(
                f"Planter {self.planter_id} config is not loaded; refresh planter list before editing max daily dosing"
            )

        try:
            payload = planter_config_set_payload(config, max_daily_dosing_s=int(value))
        except (TypeError, ValueError) as err:
            raise HomeAssistantError(f"Planter {self.planter_id} config is incomplete: {err}") from err

        await self.coordinator.async_publish_planter_set(**payload)
        await self.coordinator.async_publish_planter_get()

    def _config_payload_available(self) -> bool:
        config = _update_source(self.coordinator, self.planter_id)
        if not config:
            return False
        try:
            planter_config_set_payload(config, max_daily_dosing_s=self.native_value or 0)
        except (TypeError, ValueError):
            return False
        return True
