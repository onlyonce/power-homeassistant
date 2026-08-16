"""Config flow for Hungarian Power."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries

from .const import (
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
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
            return self.async_create_entry(title="Hungarian Power", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL_MINUTES,
                    default=DEFAULT_SCAN_INTERVAL_MINUTES,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL_MINUTES, max=MAX_SCAN_INTERVAL_MINUTES),
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

