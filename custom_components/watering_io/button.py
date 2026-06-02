from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SIGNAL_UPDATE, WateringIoCoordinator
from .entity import WateringEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: WateringIoCoordinator = hass.data[DOMAIN][entry.entry_id]
    added = False

    @callback
    def add_button() -> None:
        nonlocal added
        if added or not coordinator.hub_id_available:
            return
        async_add_entities([SensorRescanButton(coordinator)])
        added = True

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_UPDATE, add_button))
    add_button()


class SensorRescanButton(WateringEntity, ButtonEntity):
    def __init__(self, coordinator: WateringIoCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "Sensor rescan"
        self._attr_unique_id = f"{coordinator.stable_unique_prefix}_sensor_rescan"

    async def async_press(self) -> None:
        await self.coordinator.async_publish_rescan()
