"""Client for Liquipedia's MediaWiki API."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from typing import Any

import aiohttp

from .const import LIQUIPEDIA_API_URL, USER_AGENT

_BEST_OF_PATTERN = re.compile(r"\bBo\d+\b", re.IGNORECASE)
_PARSE_REQUEST_INTERVAL_SECONDS = 30


class _MatchScheduleParser(HTMLParser):
    """Extract match rows from Liquipedia's parsed Match_schedule output."""

    def __init__(self) -> None:
        """Initialize the schedule parser."""
        super().__init__()
        self.matches: list[dict[str, Any]] = []
        self._row: list[dict[str, Any]] | None = None
        self._cell: dict[str, Any] | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        """Track cells and their timestamp and team links."""
        attributes = dict(attrs)
        if tag == "tr" and "row--body" in attributes.get("class", ""):
            self._row = []
        elif self._row is not None and tag == "td":
            self._cell = {"attributes": attributes, "links": [], "text": []}
            self._row.append(self._cell)
        elif self._cell is not None and tag == "span":
            timestamp = attributes.get("data-timestamp")
            if timestamp:
                self._cell["timestamp"] = timestamp
        elif self._cell is not None and tag == "a":
            title = attributes.get("title")
            if title and not title.startswith("Match:"):
                self._cell["links"].append(title)

    def handle_endtag(self, tag: str) -> None:
        """Finish collecting a cell or a match row."""
        if tag == "td":
            self._cell = None
        elif tag == "tr" and self._row is not None:
            match = self._build_match(self._row)
            if match is not None:
                self.matches.append(match)
            self._row = None

    def handle_data(self, data: str) -> None:
        """Collect visible cell text."""
        if self._cell is not None and data.strip():
            self._cell["text"].append(data.strip())

    @staticmethod
    def _build_match(row: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Normalize one match-schedule table row."""
        if len(row) < 5:
            return None

        timestamp = row[0].get("timestamp")
        team1 = next(iter(row[2]["links"]), None)
        team2 = next(iter(row[4]["links"]), None)
        if timestamp is None or team1 is None or team2 is None:
            return None

        try:
            date = datetime.fromtimestamp(int(timestamp), timezone.utc)
        except (TypeError, ValueError, OverflowError):
            return None

        title = " ".join(row[1]["text"])
        format_text = " ".join(row[3]["text"])
        return {
            "title": title or f"{team1} vs {team2}",
            "team1": team1,
            "team2": team2,
            "date": date,
            "best_of": (
                match.group(0).upper()
                if (match := _BEST_OF_PATTERN.search(format_text))
                else None
            ),
        }


class LiquipediaAPI:
    """Fetch upcoming matches from a game-specific Liquipedia wiki."""

    _parse_locks: dict[str, asyncio.Lock] = {}
    _last_parse_requests: dict[str, float] = {}

    def __init__(self, game: str, session: aiohttp.ClientSession | None = None) -> None:
        """Initialize the API client."""
        self._session = session
        self._owns_session = session is None
        self._base_url = LIQUIPEDIA_API_URL.format(game=game)

    async def async_close(self) -> None:
        """Close a session created by this client."""
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    async def get_upcoming_matches(self, page_title: str) -> list[dict[str, Any]]:
        """Return future matches from a tournament match-schedule page."""
        matches = await self.get_matches(page_title)
        now = datetime.now(timezone.utc)
        return [match for match in matches if match["date"] >= now]

    async def get_matches(self, page_title: str) -> list[dict[str, Any]]:
        """Return matches from a tournament match-schedule page."""
        session = self._session
        if session is None:
            session = aiohttp.ClientSession(
                headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
                timeout=aiohttp.ClientTimeout(total=30),
            )
            self._session = session

        params = {
            "action": "parse",
            "format": "json",
            "page": page_title,
            "prop": "text",
        }
        await self._async_wait_for_parse_slot()
        async with session.get(self._base_url, params=params) as response:
            response.raise_for_status()
            payload = await response.json()

        if error := payload.get("error"):
            raise ValueError(error.get("info", "Liquipedia could not parse the page"))

        try:
            page_html = payload["parse"]["text"]["*"]
        except KeyError as error:
            raise ValueError("Liquipedia returned an unexpected API response") from error

        parser = _MatchScheduleParser()
        parser.feed(page_html)
        return sorted(
            parser.matches,
            key=lambda match: match["date"],
        )

    async def _async_wait_for_parse_slot(self) -> None:
        """Respect Liquipedia's one action=parse request per 30-second limit."""
        lock = self._parse_locks.setdefault(self._base_url, asyncio.Lock())
        async with lock:
            loop = asyncio.get_running_loop()
            delay = (
                self._last_parse_requests.get(self._base_url, 0)
                + _PARSE_REQUEST_INTERVAL_SECONDS
                - loop.time()
            )
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_parse_requests[self._base_url] = loop.time()
