"""Watering.IO Hub integration."""

from __future__ import annotations

from pathlib import Path

import voluptuous as vol

try:
    from homeassistant.components.http import StaticPathConfig
except ImportError:
    StaticPathConfig = None
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, PLATFORMS
from .coordinator import WateringIoCoordinator
from .helpers import extract_planter_id, planter_config_set_payload

FRONTEND_REGISTERED = "frontend_registered"
SERVICES_REGISTERED = "services_registered"
FRONTEND_URL_PATH = "/watering_io_static"
FRONTEND_PATH = Path(__file__).parent / "frontend"

SERVICE_SET_TARGET_MOISTURE = "set_target_moisture"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Watering.IO from a config entry."""
    await _async_register_frontend(hass)

    coordinator = WateringIoCoordinator(hass, entry)
    await coordinator.async_initialize()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    _async_register_services(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
        _async_unregister_services_if_unused(hass)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Register bundled dashboard card assets."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(FRONTEND_REGISTERED):
        return

    static_path = str(FRONTEND_PATH)
    if StaticPathConfig is not None and hasattr(hass.http, "async_register_static_paths"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_URL_PATH, static_path, True)]
        )
    else:
        await hass.async_add_executor_job(
            hass.http.register_static_path,
            FRONTEND_URL_PATH,
            static_path,
            True,
        )

    domain_data[FRONTEND_REGISTERED] = True


def _async_register_services(hass: HomeAssistant) -> None:
    """Register Watering.IO services once."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(SERVICES_REGISTERED):
        return

    async def async_set_target_moisture(call: ServiceCall) -> None:
        planter_id = str(call.data["planter_id"])
        target_moisture = float(call.data["target_moisture"])
        coordinator = _coordinator_for_planter(hass, planter_id)
        if coordinator is None:
            raise HomeAssistantError(f"Planter {planter_id} was not found")

        config = coordinator.state.planter_configs.get(planter_id)
        if not config:
            await coordinator.async_publish_planter_get()
            raise HomeAssistantError(
                f"Planter {planter_id} config is not loaded yet; refresh planter list and try again"
            )

        try:
            payload = planter_config_set_payload(config, target_moisture)
        except (TypeError, ValueError) as err:
            raise HomeAssistantError(f"Planter {planter_id} config is incomplete: {err}") from err

        await coordinator.async_publish_planter_set(**payload)
        await coordinator.async_publish_planter_get()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_TARGET_MOISTURE,
        async_set_target_moisture,
        schema=vol.Schema(
            {
                vol.Required("planter_id"): cv.positive_int,
                vol.Required("target_moisture"): vol.All(
                    vol.Coerce(float),
                    vol.Range(min=0, max=100),
                ),
            }
        ),
    )
    domain_data[SERVICES_REGISTERED] = True


def _async_unregister_services_if_unused(hass: HomeAssistant) -> None:
    """Remove services after the last config entry is unloaded."""
    domain_data = hass.data.get(DOMAIN, {})
    if any(isinstance(value, WateringIoCoordinator) for value in domain_data.values()):
        return
    if domain_data.get(SERVICES_REGISTERED):
        hass.services.async_remove(DOMAIN, SERVICE_SET_TARGET_MOISTURE)
        domain_data.pop(SERVICES_REGISTERED, None)


def _coordinator_for_planter(hass: HomeAssistant, planter_id: str) -> WateringIoCoordinator | None:
    """Find the coordinator that owns a planter id."""
    coordinators = [
        value for value in hass.data.get(DOMAIN, {}).values() if isinstance(value, WateringIoCoordinator)
    ]
    matches = [coordinator for coordinator in coordinators if _coordinator_has_planter(coordinator, planter_id)]
    if len(matches) == 1:
        return matches[0]
    if matches:
        return matches[0]
    return coordinators[0] if len(coordinators) == 1 else None


def _coordinator_has_planter(coordinator: WateringIoCoordinator, planter_id: str) -> bool:
    if planter_id in coordinator.state.planter_configs or planter_id in coordinator.state.planter_status:
        return True
    return any(
        extract_planter_id(planter) == planter_id
        for planter in coordinator.state.schema.get("entities", {}).get("planters", [])
    )
