"""Config flow for Hungarian Power."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    CONF_MAVIR_RETRY_INTERVAL_MINUTES,
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_MAVIR_RETRY_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MAX_MAVIR_RETRY_INTERVAL_MINUTES,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_MAVIR_RETRY_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
)


class HungarianPowerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle UI setup for the credential-free integration."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> config_entries.FlowResult:
        """Create one integration entry."""
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Hungarian Power",
                data={CONF_SCAN_INTERVAL_MINUTES: user_input[CONF_SCAN_INTERVAL_MINUTES]},
                options={
                    CONF_MAVIR_RETRY_INTERVAL_MINUTES: user_input[CONF_MAVIR_RETRY_INTERVAL_MINUTES]
                },
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL_MINUTES,
                    default=DEFAULT_SCAN_INTERVAL_MINUTES,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL_MINUTES, max=MAX_SCAN_INTERVAL_MINUTES),
                ),
                vol.Required(
                    CONF_MAVIR_RETRY_INTERVAL_MINUTES,
                    default=DEFAULT_MAVIR_RETRY_INTERVAL_MINUTES,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_MAVIR_RETRY_INTERVAL_MINUTES,
                        max=MAX_MAVIR_RETRY_INTERVAL_MINUTES,
                    ),
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow for retry configuration."""
        return HungarianPowerOptionsFlow()


class HungarianPowerOptionsFlow(config_entries.OptionsFlowWithReload):
    """Allow the user to tune polling and MAVIR's retry cooldown."""

    async def async_step_init(self, user_input: dict | None = None) -> config_entries.FlowResult:
        """Manage integration options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current_scan_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL_MINUTES,
            self.config_entry.data.get(
                CONF_SCAN_INTERVAL_MINUTES,
                DEFAULT_SCAN_INTERVAL_MINUTES,
            ),
        )
        current_retry_interval = self.config_entry.options.get(
            CONF_MAVIR_RETRY_INTERVAL_MINUTES,
            self.config_entry.data.get(
                CONF_MAVIR_RETRY_INTERVAL_MINUTES,
                DEFAULT_MAVIR_RETRY_INTERVAL_MINUTES,
            ),
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL_MINUTES,
                    default=current_scan_interval,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_SCAN_INTERVAL_MINUTES,
                        max=MAX_SCAN_INTERVAL_MINUTES,
                    ),
                ),
                vol.Required(
                    CONF_MAVIR_RETRY_INTERVAL_MINUTES,
                    default=current_retry_interval,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_MAVIR_RETRY_INTERVAL_MINUTES,
                        max=MAX_MAVIR_RETRY_INTERVAL_MINUTES,
                    ),
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
