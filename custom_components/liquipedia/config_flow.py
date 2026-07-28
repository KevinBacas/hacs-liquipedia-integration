"""Config flow for Liquipedia integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_GAME,
    CONF_TOURNAMENT,
    DEFAULT_GAME,
    SUPPORTED_GAMES,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default="Liquipedia"): str,
        vol.Required(CONF_GAME, default=DEFAULT_GAME): vol.In(SUPPORTED_GAMES),
        vol.Required(CONF_TOURNAMENT): vol.All(str, vol.Strip, vol.Length(min=1)),
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Liquipedia."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        if user_input[CONF_GAME] not in SUPPORTED_GAMES:
            errors[CONF_GAME] = "invalid_game"

        if not errors:
            # Create a unique ID based on the game and tournament
            unique_id = f"{user_input[CONF_GAME]}_{user_input[CONF_TOURNAMENT]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )
