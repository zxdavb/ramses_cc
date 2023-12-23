"""Config flow to configure Ramses integration."""

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class RamsesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Ramses."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initiated by the user."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title="Gateway", data=user_input[DOMAIN])

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Optional(DOMAIN): selector.ObjectSelector()}),
        )

    async def async_step_import(self, import_data):
        """Import entry from configuration.yaml."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        import_data[CONF_SCAN_INTERVAL] = import_data[CONF_SCAN_INTERVAL].seconds
        return self.async_create_entry(title="Gateway", data=import_data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        """Options callback for Ramses."""
        return RamsesOptionsFlow(config_entry)


class RamsesOptionsFlow(OptionsFlow):
    """Options flow options for Ramses."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize AccuWeather options flow."""
        self.config_entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=user_input[DOMAIN]
            )
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(self.config_entry.entry_id)
            )
            return self.async_create_entry(title="", data=None)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        DOMAIN,
                        default=dict(self.config_entry.data),
                    ): selector.ObjectSelector()
                }
            ),
        )
