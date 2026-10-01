"""Config flow for Liquipedia integration."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .api import LiquipediaAPI
from .const import DOMAIN, CONF_GAME, CONF_TOURNAMENT, DEFAULT_GAME, SUPPORTED_GAMES

_MANUAL = "manual-entry"
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default="Liquipedia"): str,
        vol.Required(CONF_GAME, default=DEFAULT_GAME): vol.In(SUPPORTED_GAMES),
    }
)
_MANUAL_SCHEMA = vol.Schema(
    {vol.Required(CONF_TOURNAMENT): vol.All(str, vol.Strip, vol.Length(min=1))}
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Liquipedia."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._tournaments: dict[str, str] = {}
        self._api: LiquipediaAPI | None = None
        self._discovery_error: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the game before loading its tournaments."""
        errors = {}
        if user_input is not None:
            if user_input[CONF_GAME] not in SUPPORTED_GAMES:
                errors[CONF_GAME] = "invalid_game"
            else:
                self._data = dict(user_input)
                self._api = LiquipediaAPI(
                    user_input[CONF_GAME], async_get_clientsession(self.hass)
                )
                self._discovery_error = None
                try:
                    self._tournaments = await self._api.get_tournaments()
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                    self._tournaments = {}
                    self._discovery_error = "cannot_connect"
                return await self.async_step_tournament()
        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_tournament(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select a discovered tournament or choose manual setup."""
        errors = {}
        if user_input is not None:
            tournament = user_input[CONF_TOURNAMENT]
            if tournament == _MANUAL:
                return await self.async_step_manual()
            if tournament not in self._tournaments:
                errors[CONF_TOURNAMENT] = "invalid_tournament"
            else:
                assert self._api is not None
                try:
                    page = await self._api.get_schedule_page(tournament)
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    errors["base"] = "cannot_connect"
                except ValueError:
                    errors["base"] = "no_schedule"
                else:
                    return await self._async_create_tournament_entry(page)
        elif self._discovery_error:
            errors["base"] = self._discovery_error
        elif not self._tournaments:
            errors["base"] = "no_tournaments"
        is_french = self.hass.config.language == "fr"
        options = [
            {
                "value": title,
                "label": (
                    label.replace("(Upcoming)", "(À venir)").replace("(Ongoing)", "(En cours)")
                    if is_french else label
                ),
            }
            for title, label in self._tournaments.items()
        ]
        options.append({"value": _MANUAL, "label": "manual"})
        return self.async_show_form(
            step_id="tournament",
            data_schema=vol.Schema({
                vol.Required(CONF_TOURNAMENT): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="tournament",
                    )
                )
            }),
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow schedules absent from the discovery list."""
        if user_input is not None:
            return await self._async_create_tournament_entry(
                user_input[CONF_TOURNAMENT].strip()
            )
        return self.async_show_form(step_id="manual", data_schema=_MANUAL_SCHEMA)

    async def _async_create_tournament_entry(self, page: str) -> ConfigFlowResult:
        """Preserve the stored schedule title and existing duplicate detection."""
        await self.async_set_unique_id(f"{self._data[CONF_GAME]}_{page}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=self._data[CONF_NAME], data={**self._data, CONF_TOURNAMENT: page}
        )
