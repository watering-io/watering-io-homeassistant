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


class WateringIoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Watering.IO Hub."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return WateringIoOptionsFlow(config_entry)

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

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        """Manage integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

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
        return self.async_show_form(step_id="init", data_schema=schema)
