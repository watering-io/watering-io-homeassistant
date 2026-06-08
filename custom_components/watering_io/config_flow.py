"""Config flow for Watering.IO Hub."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_PUMP_1_FLOW_ML_PER_S,
    DEFAULT_PREFIX,
    DEFAULT_PUMP_1_FLOW_ML_PER_S,
    DOMAIN,
)
from .coordinator import WateringIoCoordinator

CONF_ENABLED = "enabled"
CONF_FERTILIZER_STEPS = "fertilizer_steps"
CONF_HYSTERESIS = "hysteresis"
CONF_MAX_DAILY_DOSING_S = "max_daily_dosing_s"
CONF_PLANTER_ID = "planter_id"
CONF_SENSOR_MODBUS_ID = "sensor_modbus_id"
CONF_TARGET_MOISTURE = "target_moisture"
CONF_VALVE_ROUTE = "valve_route"

MENU_OPTIONS = {
    "pump_calibration": "Pump calibration",
    "planter_set": "Add or update planter",
    "planter_delete": "Delete planter",
    "refresh_planters": "Refresh planter list",
}


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
            prefix = (user_input.get("topic_prefix") or DEFAULT_PREFIX).strip()
            await self.async_set_unique_id(prefix.lower())
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Watering.IO Hub",
                data={"topic_prefix": prefix},
            )

        schema = vol.Schema(
            {
                vol.Required("topic_prefix", default=DEFAULT_PREFIX): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)


class WateringIoOptionsFlow(config_entries.OptionsFlow):
    """Handle Watering.IO options."""

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        """Manage integration options."""
        return self.async_show_menu(step_id="init", menu_options=MENU_OPTIONS)

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
