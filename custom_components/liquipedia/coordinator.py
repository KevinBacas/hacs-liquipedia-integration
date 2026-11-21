"""Fetch and combine Liquipedia schedules for a Home Assistant entry."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any
from urllib.parse import quote

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import LiquipediaAPI
from .const import (
    CONF_GAME,
    CONF_MODE,
    CONF_TEAM_FILTER,
    CONF_TEAM_NAME,
    CONF_TEAM_PAGES,
    CONF_TOURNAMENT,
    DEFAULT_UPDATE_INTERVAL,
    LIQUIPEDIA_BASE_URL,
    MODE_TEAM,
)

_LOGGER = logging.getLogger(__name__)
_SOURCE_ERRORS = (aiohttp.ClientError, TimeoutError, ValueError)
_STATUS_PRIORITY = {"live": 1, "finished": 2}


def _team_key(title: str) -> str:
    """Compare wiki titles independently of case, underscores and spacing."""
    return " ".join(title.replace("_", " ").split()).casefold()


@dataclass(frozen=True)
class MatchSnapshot:
    """The most recent successful data and which games failed to refresh."""

    matches: tuple[dict[str, Any], ...]
    updated_at: datetime
    unavailable_games: tuple[str, ...] = ()


class LiquipediaDataUpdateCoordinator(DataUpdateCoordinator[MatchSnapshot]):
    """Poll a tournament or the selected games of a team."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        config = {**config_entry.data, **config_entry.options}
        self.team_mode = config.get(CONF_MODE) == MODE_TEAM
        self.tournament = config.get(CONF_TOURNAMENT, "")
        self._team_filter = _team_key(config.get(CONF_TEAM_FILTER) or "")
        session = async_get_clientsession(hass)
        if self.team_mode:
            self._team_pages: dict[str, str] = config[CONF_TEAM_PAGES]
            self.label = config[CONF_TEAM_NAME]
            self._clients = {
                game: LiquipediaAPI(game, session) for game in self._team_pages
            }
        else:
            game = config[CONF_GAME]
            self.label = game.title()
            self._clients = {game: LiquipediaAPI(game, session)}

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"Liquipedia {self.label}",
            update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL),
        )

    async def _async_update_data(self) -> MatchSnapshot:
        if self.team_mode:
            return await self._async_update_team()

        client = next(iter(self._clients.values()))
        try:
            matches = await client.get_matches(self.tournament)
        except _SOURCE_ERRORS as exception:
            raise UpdateFailed(str(exception)) from exception
        if self._team_filter:
            matches = [
                match for match in matches
                if self._team_filter in (_team_key(match["team1"]), _team_key(match["team2"]))
            ]
        return MatchSnapshot(tuple(matches), dt_util.utcnow())

    async def _async_update_team(self) -> MatchSnapshot:
        results = await asyncio.gather(
            *(client.get_team_matches(self._team_pages[game]) for game, client in self._clients.items()),
            return_exceptions=True,
        )
        matches = {}
        unavailable = []
        for game, result in zip(self._clients, results, strict=True):
            if isinstance(result, _SOURCE_ERRORS):
                unavailable.append(game)
                _LOGGER.debug("Could not refresh Liquipedia for %s: %s", game, result)
                continue
            if isinstance(result, BaseException):
                raise result
            for match in result:
                key = (
                    game,
                    match.get("tournament_page") or match.get("tournament"),
                    match["date"],
                    frozenset((_team_key(match["team1"]), _team_key(match["team2"]))),
                )
                previous = matches.get(key)
                priority = _STATUS_PRIORITY.get(match.get("status"), 0)
                if previous is None or priority > _STATUS_PRIORITY.get(previous.get("status"), 0):
                    matches[key] = {**match, "game": game}

        if len(unavailable) == len(self._clients):
            raise UpdateFailed(f"Could not refresh Liquipedia for {', '.join(unavailable)}")
        return MatchSnapshot(
            tuple(sorted(matches.values(), key=lambda match: (match["date"], match["game"]))),
            dt_util.utcnow(),
            tuple(unavailable),
        )

    def match_attributes(self, match: dict[str, Any] | None) -> dict[str, Any]:
        """Show Liquipedia attribution and, for teams, coverage across games."""
        attributes: dict[str, Any] = {}
        if self.team_mode and self.data is not None:
            attributes.update(
                data_complete=not self.data.unavailable_games,
                unavailable_games=list(self.data.unavailable_games),
            )
        if match is not None:
            if self.team_mode:
                game = match["game"]
                page = self._team_pages[game]
                attributes.update(
                    game=game,
                    tournament=match.get("tournament"),
                    opponent=match.get("opponent"),
                )
            else:
                game = next(iter(self._clients))
                page = self.tournament
            slug = quote(page.replace(" ", "_"))
            attributes.update(attribution="Data provided by Liquipedia", source_url=f"{LIQUIPEDIA_BASE_URL}/{game}/{slug}")
        return attributes
