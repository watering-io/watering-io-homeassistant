"""Base entities for watering_io."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import SIGNAL_UPDATE, WateringIoCoordinator


class WateringEntity(Entity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: WateringIoCoordinator) -> None:
        self.coordinator = coordinator

    @property
    def available(self) -> bool:
        return self.coordinator.device_available

    @property
    def device_info(self) -> DeviceInfo:
        return self.coordinator.hub_device_info

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_UPDATE,
                self._async_handle_update,
            )
        )

    @callback
    def _async_handle_update(self) -> None:
        self.schedule_update_ha_state()


class WateringPlanterEntity(WateringEntity):
    def __init__(self, coordinator: WateringIoCoordinator, planter_id: str) -> None:
        super().__init__(coordinator)
        self.planter_id = planter_id
        self.planter_unique_id = coordinator.planter_unique_id(planter_id) or f"unknown_planter_{planter_id}"

    @property
    def device_info(self) -> DeviceInfo:
        return self.coordinator.planter_device_info(self.planter_id, self.planter_unique_id)
