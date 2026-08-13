"""Config flow for Watering.IO Hub."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_HUB_ID,
    CONF_PUMP_1_FLOW_ML_PER_S,
    DEFAULT_PREFIX,
    DEFAULT_PUMP_1_FLOW_ML_PER_S,
    DOMAIN,
)
from .coordinator import WateringIoCoordinator
from .helpers import configured_topic_root

CONF_ENABLED = "enabled"
CONF_FERTILIZER_STEPS = "fertilizer_steps"
CONF_HYSTERESIS = "hysteresis"
CONF_MAX_DAILY_DOSING_S = "max_daily_dosing_s"
CONF_PLANTER_ID = "planter_id"
CONF_SENSOR_MODBUS_ID = "sensor_modbus_id"
CONF_TARGET_MOISTURE = "target_moisture"
CONF_VALVE_ROUTE = "valve_route"

MENU_OPTIONS = {
    "hub_settings": "Hub MQTT settings",
    "pump_calibration": "Pump calibration",
    "planter_set": "Add or update planter",
    "planter_delete": "Delete planter",
    "refresh_planters": "Refresh planter list",
}


def _normalize_hub_settings(topic_prefix: str, hub_id: str | None = None) -> tuple[str, str | None]:
    """Normalize MQTT root and optional explicit hub id."""
    root, embedded_hub_id = configured_topic_root(topic_prefix or DEFAULT_PREFIX)
    selected_hub_id = (hub_id or "").strip() or embedded_hub_id
    return root or DEFAULT_PREFIX, selected_hub_id


def _hub_entry_data(topic_prefix: str, hub_id: str | None) -> dict[str, str]:
    """Build config entry data without storing empty hub ids."""
    data = {"topic_prefix": topic_prefix}
    if hub_id:
        data[CONF_HUB_ID] = hub_id
    return data


def _hub_entry_title(hub_id: str | None) -> str:
    """Build the Home Assistant config entry title."""
    return f"Watering.IO Hub {hub_id}" if hub_id else "Watering.IO Hub"


def _hub_unique_id(topic_prefix: str, hub_id: str | None) -> str:
    """Build a unique id that allows multiple hubs below the same MQTT root."""
    root = topic_prefix.rstrip("/").lower()
    if not hub_id:
        return root
    return f"{root}::hub::{hub_id.strip().lower()}"


class WateringIoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Watering.IO Hub."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return WateringIoOptionsFlow()

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            prefix, hub_id = _normalize_hub_settings(
                user_input.get("topic_prefix") or DEFAULT_PREFIX,
                user_input.get(CONF_HUB_ID),
            )
            await self.async_set_unique_id(_hub_unique_id(prefix, hub_id))
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=_hub_entry_title(hub_id),
                data=_hub_entry_data(prefix, hub_id),
            )

        schema = vol.Schema(
            {
                vol.Required("topic_prefix", default=DEFAULT_PREFIX): str,
                vol.Optional(CONF_HUB_ID, default=""): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)


class WateringIoOptionsFlow(config_entries.OptionsFlow):
    """Handle Watering.IO options."""

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        """Manage integration options."""
        return self.async_show_menu(step_id="init", menu_options=MENU_OPTIONS)

    async def async_step_hub_settings(self, user_input: dict | None = None) -> FlowResult:
        """Manage MQTT root and explicit hub id."""
        if user_input is not None:
            prefix, hub_id = _normalize_hub_settings(
                user_input.get("topic_prefix") or DEFAULT_PREFIX,
                user_input.get(CONF_HUB_ID),
            )
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=_hub_entry_data(prefix, hub_id),
                title=_hub_entry_title(hub_id),
                unique_id=_hub_unique_id(prefix, hub_id),
            )
            return self.async_create_entry(title="", data=dict(self.config_entry.options))

        prefix, hub_id = _normalize_hub_settings(
            self.config_entry.data.get("topic_prefix", DEFAULT_PREFIX),
            self.config_entry.data.get(CONF_HUB_ID),
        )
        schema = vol.Schema(
            {
                vol.Required("topic_prefix", default=prefix): str,
                vol.Optional(CONF_HUB_ID, default=hub_id or ""): str,
            }
        )
        return self.async_show_form(step_id="hub_settings", data_schema=schema)

    async def async_step_pump_calibration(self, user_input: dict | None = None) -> FlowResult:
        """Manage pump calibration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data={**self.config_entry.options, **user_input})

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PUMP_1_FLOW_ML_PER_S,
                    default=self.config_entry.options.get(
                        CONF_PUMP_1_FLOW_ML_PER_S,
                        DEFAULT_PUMP_1_FLOW_ML_PER_S,
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=0)),
            }
        )
        return self.async_show_form(step_id="pump_calibration", data_schema=schema)

    async def async_step_planter_set(self, user_input: dict | None = None) -> FlowResult:
        """Add or update a planter configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            coordinator = self._coordinator()
            if coordinator is None:
                errors["base"] = "integration_not_loaded"
            else:
                await coordinator.async_publish_planter_set(
                    planter_id=user_input[CONF_PLANTER_ID],
                    enabled=user_input[CONF_ENABLED],
                    sensor_modbus_id=user_input[CONF_SENSOR_MODBUS_ID],
                    valve_route=user_input[CONF_VALVE_ROUTE],
                    target_moisture=user_input[CONF_TARGET_MOISTURE],
                    hysteresis=user_input[CONF_HYSTERESIS],
                    fertilizer_steps=user_input[CONF_FERTILIZER_STEPS],
                    max_daily_dosing_s=user_input[CONF_MAX_DAILY_DOSING_S],
                )
                await coordinator.async_publish_planter_get()
                return self.async_create_entry(title="", data=dict(self.config_entry.options))

        schema = vol.Schema(
            {
                vol.Required(CONF_PLANTER_ID): vol.All(vol.Coerce(int), vol.Range(min=1)),
                vol.Required(CONF_ENABLED, default=True): bool,
                vol.Required(CONF_SENSOR_MODBUS_ID): vol.All(vol.Coerce(int), vol.Range(min=1)),
                vol.Required(CONF_VALVE_ROUTE): vol.All(vol.Coerce(int), vol.Range(min=0)),
                vol.Required(CONF_TARGET_MOISTURE, default=45.0): vol.All(
                    vol.Coerce(float),
                    vol.Range(min=0, max=100),
                ),
                vol.Required(CONF_FERTILIZER_STEPS, default=0): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=0),
                ),
                vol.Required(CONF_MAX_DAILY_DOSING_S, default=300): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=0, max=86400),
                ),
                vol.Required(CONF_HYSTERESIS, default=5.0): vol.All(
                    vol.Coerce(float),
                    vol.Range(min=0, max=100),
                ),
            }
        )
        return self.async_show_form(step_id="planter_set", data_schema=schema, errors=errors)

    async def async_step_planter_delete(self, user_input: dict | None = None) -> FlowResult:
        """Delete one planter configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            coordinator = self._coordinator()
            if coordinator is None:
                errors["base"] = "integration_not_loaded"
            else:
                await coordinator.async_publish_planter_delete(user_input[CONF_PLANTER_ID])
                await coordinator.async_publish_planter_get()
                return self.async_create_entry(title="", data=dict(self.config_entry.options))

        schema = vol.Schema(
            {
                vol.Required(CONF_PLANTER_ID): vol.All(vol.Coerce(int), vol.Range(min=1)),
            }
        )
        return self.async_show_form(step_id="planter_delete", data_schema=schema, errors=errors)

    async def async_step_refresh_planters(self, user_input: dict | None = None) -> FlowResult:
        """Request the current planter configuration list from the hub."""
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(title="", data=dict(self.config_entry.options))

        coordinator = self._coordinator()
        if coordinator is None:
            errors["base"] = "integration_not_loaded"
        else:
            await coordinator.async_publish_planter_get()

        return self.async_show_form(
            step_id="refresh_planters",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={
                "planter_count": str(len(coordinator.state.planter_configs) if coordinator else 0),
            },
        )

    def _coordinator(self) -> WateringIoCoordinator | None:
        """Return the active coordinator for this config entry."""
        return self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
