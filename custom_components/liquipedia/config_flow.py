"""Config flow for Liquipedia integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import LiquipediaAPI, ScheduleNotFoundError, TeamNotFoundError
from .const import (
    CONF_GAME,
    CONF_MODE,
    CONF_TEAM_FILTER,
    CONF_TEAM_NAME,
    CONF_TEAM_PAGES,
    CONF_TOURNAMENT,
    DEFAULT_GAME,
    DOMAIN,
    MODE_TEAM,
    MODE_TOURNAMENT,
    SUPPORTED_GAMES,
    TEAM_GAMES,
)
from .team_parser import normalize_title

_LOGGER = logging.getLogger(__name__)
_MANUAL = "manual-entry"
_CONF_GAMES = "games"
_CONF_TEAM_MATCH = "team_match"
_CONF_TEAM_PAGE = "team_page"
_API_ERRORS = (aiohttp.ClientError, TimeoutError, ValueError)
_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MODE): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[MODE_TEAM, MODE_TOURNAMENT], translation_key="mode"
            )
        )
    }
)
_TOURNAMENT_GAME_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_GAME, default=DEFAULT_GAME): vol.In(SUPPORTED_GAMES),
        vol.Optional(CONF_TEAM_FILTER): str,
    }
)
_MANUAL_SCHEMA = vol.Schema({vol.Required(CONF_TOURNAMENT): str})
_TEAM_NAME_SCHEMA = vol.Schema({vol.Required(CONF_TEAM_NAME): str})
_TEAM_GAMES_SCHEMA = vol.Schema(
    {
        vol.Required(_CONF_GAMES): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": game, "label": label} for game, label in TEAM_GAMES.items()
                ],
                multiple=True,
                mode=selector.SelectSelectorMode.LIST,
            )
        )
    }
)
_TEAM_FILTER_SCHEMA = vol.Schema({vol.Optional(CONF_TEAM_FILTER): str})


def _schedule_key(page: str) -> str:
    """Compare canonical titles with legacy MediaWiki title spellings."""
    title = normalize_title(page)
    return title[:1].upper() + title[1:]


class _TeamFlow(config_entries.ConfigEntryBaseFlow):
    """Share game selection and team page confirmation between flows."""

    def __init__(self) -> None:
        self._team_name = ""
        self._existing_team_pages: dict[str, str] = {}
        self._team_pages: dict[str, str] = {}
        self._remaining_games: list[str] = []
        self._team_candidates: list[str] = []
        self._team_search_error: str | None = None

    def _api_for_game(self, game: str) -> LiquipediaAPI:
        """Use the shared Home Assistant HTTP session for a game wiki."""
        return LiquipediaAPI(game, async_get_clientsession(self.hass))

    async def async_step_team_games(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the game wikis to follow for the organization."""
        errors = {}
        if user_input is not None:
            games = user_input[_CONF_GAMES]
            if games and all(game in TEAM_GAMES for game in games):
                self._team_pages = {}
                self._remaining_games = list(dict.fromkeys(games))
                return await self._async_next_team_game()
            errors[_CONF_GAMES] = "invalid_team_games"
        return self.async_show_form(
            step_id="team_games",
            data_schema=self.add_suggested_values_to_schema(
                _TEAM_GAMES_SCHEMA, {_CONF_GAMES: list(self._existing_team_pages)}
            ),
            errors=errors,
            description_placeholders={"team_name": self._team_name},
            last_step=False,
        )

    async def _async_next_team_game(self) -> ConfigFlowResult:
        """Find the next game's candidates or persist the confirmed pages."""
        if not self._remaining_games:
            return await self._async_save_team()

        self._team_search_error = None
        self._team_candidates = []
        game = self._remaining_games[0]
        if page := self._existing_team_pages.get(game):
            self._team_candidates = [page]
        else:
            try:
                self._team_candidates = await self._api_for_game(game).search_teams(
                    self._team_name
                )
            except _API_ERRORS:
                self._team_search_error = "cannot_search_team"
            except Exception:
                _LOGGER.exception("Unexpected error searching for Liquipedia teams")
                self._team_search_error = "unknown"
        return await self.async_step_team_page()

    async def async_step_team_page(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered team or enter its Liquipedia page title."""
        game = self._remaining_games[0]
        errors = {}
        if user_input is not None:
            team_page = user_input.get(_CONF_TEAM_PAGE, "").strip()
            team_match = user_input.get(_CONF_TEAM_MATCH)
            page = None
            if team_page:
                try:
                    page = await self._api_for_game(game).resolve_team(team_page)
                except TeamNotFoundError:
                    errors[_CONF_TEAM_PAGE] = "invalid_team_page"
                except _API_ERRORS:
                    errors["base"] = "cannot_connect_team"
                except Exception:
                    _LOGGER.exception("Unexpected error resolving a Liquipedia team page")
                    errors["base"] = "unknown"
            elif team_match in self._team_candidates:
                page = team_match
            else:
                field = _CONF_TEAM_MATCH if self._team_candidates else _CONF_TEAM_PAGE
                errors[field] = "invalid_team_page"
            if page is not None:
                self._team_pages[game] = page
                self._remaining_games.pop(0)
                return await self._async_next_team_game()
        elif self._team_search_error:
            errors["base"] = self._team_search_error

        fields = {}
        if self._team_candidates:
            fields[vol.Optional(_CONF_TEAM_MATCH)] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=self._team_candidates,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
            fields[vol.Optional(_CONF_TEAM_PAGE)] = str
        else:
            fields[vol.Required(_CONF_TEAM_PAGE)] = str
        suggested = user_input
        if user_input is None and len(self._team_candidates) == 1:
            suggested = {_CONF_TEAM_MATCH: self._team_candidates[0]}
        return self.async_show_form(
            step_id="team_page",
            data_schema=self.add_suggested_values_to_schema(vol.Schema(fields), suggested),
            errors=errors,
            description_placeholders={"team_name": self._team_name, "game": TEAM_GAMES[game]},
            last_step=len(self._remaining_games) == 1,
        )

    async def _async_save_team(self) -> ConfigFlowResult:
        """Persist the team pages through the active flow."""
        raise NotImplementedError


class ConfigFlow(_TeamFlow, config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Liquipedia."""

    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._data: dict[str, Any] = {}
        self._tournaments: dict[str, str] = {}
        self._api: LiquipediaAPI | None = None
        self._discovery_error: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose whether to follow an organization or a tournament."""
        errors = {}
        if user_input is not None:
            mode = user_input[CONF_MODE]
            if mode == MODE_TEAM:
                return await self.async_step_team_name()
            if mode == MODE_TOURNAMENT:
                return await self.async_step_tournament_game()
            errors[CONF_MODE] = "invalid_mode"
        return self.async_show_form(
            step_id="user", data_schema=_MODE_SCHEMA, errors=errors, last_step=False
        )

    async def async_step_team_name(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the organization name before selecting games."""
        errors = {}
        if user_input is not None:
            team_name = " ".join(user_input[CONF_TEAM_NAME].split())
            if team_name:
                await self.async_set_unique_id(f"team_{team_name.casefold()}")
                self._abort_if_unique_id_configured()
                self._team_name = team_name
                return await self.async_step_team_games()
            errors[CONF_TEAM_NAME] = "invalid_team_name"
        return self.async_show_form(
            step_id="team_name", data_schema=_TEAM_NAME_SCHEMA, errors=errors, last_step=False
        )

    async def _async_save_team(self) -> ConfigFlowResult:
        """Create the organization entry with canonical titles for each game."""
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=self._team_name,
            data={
                CONF_MODE: MODE_TEAM,
                CONF_TEAM_NAME: self._team_name,
                CONF_TEAM_PAGES: self._team_pages,
            },
        )

    async def async_step_tournament_game(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the game before loading its tournaments."""
        errors = {}
        if user_input is not None:
            if user_input[CONF_GAME] not in SUPPORTED_GAMES:
                errors[CONF_GAME] = "invalid_game"
            else:
                self._data = {
                    CONF_MODE: MODE_TOURNAMENT,
                    CONF_GAME: user_input[CONF_GAME],
                }
                if team_filter := user_input.get(CONF_TEAM_FILTER, "").strip():
                    self._data[CONF_TEAM_FILTER] = team_filter
                self._api = self._api_for_game(user_input[CONF_GAME])
                self._discovery_error = None
                try:
                    self._tournaments = await self._api.get_tournaments()
                except _API_ERRORS:
                    self._tournaments = {}
                    self._discovery_error = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected error loading Liquipedia tournaments")
                    self._tournaments = {}
                    self._discovery_error = "unknown"
                return await self.async_step_tournament()
        return self.async_show_form(
            step_id="tournament_game",
            data_schema=_TOURNAMENT_GAME_SCHEMA,
            errors=errors,
            last_step=False,
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
                except ScheduleNotFoundError:
                    errors["base"] = "no_schedule"
                except _API_ERRORS:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected error resolving a Liquipedia schedule")
                    errors["base"] = "unknown"
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
        options.append({"value": _MANUAL, "label": "Enter a schedule manually"})
        return self.async_show_form(
            step_id="tournament",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOURNAMENT): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="tournament",
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow schedules absent from the discovery list."""
        errors = {}
        if user_input is not None:
            if title := user_input[CONF_TOURNAMENT].strip():
                assert self._api is not None
                try:
                    page = await self._api.get_schedule_page(title)
                except ScheduleNotFoundError:
                    errors[CONF_TOURNAMENT] = "invalid_schedule"
                except _API_ERRORS:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected error resolving a Liquipedia schedule")
                    errors["base"] = "unknown"
                else:
                    return await self._async_create_tournament_entry(page)
            else:
                errors[CONF_TOURNAMENT] = "invalid_schedule"
        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(_MANUAL_SCHEMA, user_input),
            errors=errors,
        )

    async def _async_create_tournament_entry(self, page: str) -> ConfigFlowResult:
        """Create a schedule entry if its page is not already configured."""
        game = self._data[CONF_GAME]
        key = _schedule_key(page)
        await self.async_set_unique_id(f"{game}_{key}")
        self._abort_if_unique_id_configured()
        for entry in self._async_current_entries():
            if (
                entry.data.get(CONF_GAME) == game
                and (saved_page := entry.data.get(CONF_TOURNAMENT))
                and _schedule_key(saved_page) == key
            ):
                return self.async_abort(reason="already_configured")
        return self.async_create_entry(
            title=page.removesuffix("/Match Schedule"),
            data={**self._data, CONF_TOURNAMENT: page},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> config_entries.OptionsFlow:
        """Offer options for new and existing Liquipedia entries."""
        return LiquipediaOptionsFlow()


class LiquipediaOptionsFlow(_TeamFlow, config_entries.OptionsFlowWithReload):
    """Edit followed games or the team filter for a tournament."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show mode-specific settings for this entry."""
        entry = self.config_entry
        settings = {**entry.data, **entry.options}
        if settings.get(CONF_MODE) == MODE_TEAM:
            self._team_name = settings[CONF_TEAM_NAME]
            self._existing_team_pages = settings[CONF_TEAM_PAGES]
            return await self.async_step_team_games(user_input)
        if user_input is not None:
            team_filter = user_input.get(CONF_TEAM_FILTER, "").strip()
            options = dict(entry.options)
            if team_filter != settings.get(CONF_TEAM_FILTER, ""):
                options[CONF_TEAM_FILTER] = team_filter
            return self.async_create_entry(data=options)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(_TEAM_FILTER_SCHEMA, settings),
        )

    async def _async_save_team(self) -> ConfigFlowResult:
        """Replace the configured games while keeping the existing entry."""
        options = dict(self.config_entry.options)
        if self._team_pages != self._existing_team_pages:
            options[CONF_TEAM_PAGES] = self._team_pages
        return self.async_create_entry(data=options)
