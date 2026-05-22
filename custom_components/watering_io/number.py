from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SIGNAL_UPDATE, WateringIoCoordinator
from .entity import WateringPlanterEntity
from .helpers import coerce_numeric, extract_planter_id, planter_config_set_payload


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: WateringIoCoordinator = hass.data[DOMAIN][entry.entry_id]
    added_planters: set[str] = set()

    @callback
    def add_dynamic() -> None:
        new_entities = []
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
            new_entities.append(PlanterTargetMoistureNumber(coordinator, planter_id))

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_UPDATE, add_dynamic))
    add_dynamic()
    await coordinator.async_publish_planter_get()


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
        config = self.coordinator.state.planter_configs.get(self.planter_id)
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
        config = self.coordinator.state.planter_configs.get(self.planter_id)
        if not config:
            return False
        try:
            planter_config_set_payload(config, self.native_value or 0)
        except (TypeError, ValueError):
            return False
        return True
