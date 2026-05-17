"""Watering.IO Hub integration."""

from __future__ import annotations

from pathlib import Path

try:
    from homeassistant.components.http import StaticPathConfig
except ImportError:
    StaticPathConfig = None
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import WateringIoCoordinator

FRONTEND_REGISTERED = "frontend_registered"
FRONTEND_URL_PATH = "/watering_io_static"
FRONTEND_PATH = Path(__file__).parent / "frontend"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Watering.IO from a config entry."""
    await _async_register_frontend(hass)

    coordinator = WateringIoCoordinator(hass, entry)
    await coordinator.async_initialize()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
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
