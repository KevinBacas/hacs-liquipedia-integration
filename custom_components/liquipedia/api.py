"""Client for Liquipedia's MediaWiki API."""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit
from weakref import WeakKeyDictionary

import aiohttp

from .const import LIQUIPEDIA_API_URL, USER_AGENT
from .team_parser import BEST_OF_PATTERN, TeamPageParser, normalize_title

_PARSE_REQUEST_INTERVAL_SECONDS = 30
_REQUEST_INTERVAL_SECONDS = 2
_MAX_PARSE_WAIT_SECONDS = 125
_PARSE_CACHE_SECONDS = 120
_PARSE_CACHE_SIZE = 32
_TEAM_INFOBOX = "Template:Infobox team"

_ParseKey = tuple[str, tuple[tuple[str, str], ...]]


class TeamNotFoundError(ValueError):
    """The supplied title does not identify a team on the game wiki."""


@dataclass
class _PendingParse:
    task: asyncio.Task[dict[str, Any]]
    waiters: int = 0


@dataclass
class _HostRequests:
    next_request: float = 0
    next_parse: float = 0
    request_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    parse_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    parses: dict[_ParseKey, _PendingParse] = field(default_factory=dict)
    cache: OrderedDict[_ParseKey, tuple[float, dict[str, Any]]] = field(
        default_factory=OrderedDict,
    )


class _MatchScheduleParser(HTMLParser):
    """Extract match rows from Liquipedia's parsed Match_schedule output."""

    def __init__(self) -> None:
        """Initialize the schedule parser."""
        super().__init__()
        self.matches: list[dict[str, Any]] = []
        self._row: list[dict[str, Any]] | None = None
        self._row_status_values: list[str] = []
        self._cell: dict[str, Any] | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        """Track cells and their timestamp and team links."""
        attributes = dict(attrs)
        if tag == "tr" and "row--body" in attributes.get("class", ""):
            self._row = []
            self._row_status_values = self._get_status_values(attributes)
        elif self._row is not None:
            self._row_status_values.extend(self._get_status_values(attributes))
            if tag == "td":
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
            match = self._build_match(
                self._row,
                self._row_status_values,
            )
            if match is not None:
                self.matches.append(match)
            self._row = None
            self._row_status_values = []

    def handle_data(self, data: str) -> None:
        """Collect visible cell text."""
        if self._cell is not None and data.strip():
            self._cell["text"].append(data.strip())

    @staticmethod
    def _get_status_values(attributes: dict[str, str | None]) -> list[str]:
        """Return explicit status markers attached to a schedule element."""
        values = [
            attributes[key]
            for key in (
                "data-status",
                "data-match-status",
                "data-state",
                "data-match-state",
            )
            if attributes.get(key)
        ]
        if class_name := attributes.get("class"):
            values.append(class_name)
        return values

    @staticmethod
    def _get_match_status(status_values: list[str]) -> str:
        """Normalize an explicit status marker from Liquipedia's markup.

        A start time alone is not evidence that a match is live.  Keep the
        status unknown unless the source itself marks the match as live or
        complete.
        """
        status = " ".join(status_values).lower().replace("_", "-")
        if any(
            value in status for value in ("live", "ongoing", "in-progress", "running")
        ):
            return "live"
        if any(
            value in status
            for value in (
                "finished",
                "completed",
                "cancelled",
                "canceled",
                "notplayed",
            )
        ):
            return "finished"
        return "unknown"

    @staticmethod
    def _build_match(
        row: list[dict[str, Any]],
        status_values: list[str],
    ) -> dict[str, Any] | None:
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
            "status": _MatchScheduleParser._get_match_status(status_values),
            "best_of": (
                match.group(0).upper()
                if (match := BEST_OF_PATTERN.search(format_text))
                else None
            ),
        }


class _TournamentListParser(HTMLParser):
    """Read the names and dates from Liquipedia's tournament ticker."""

    def __init__(self) -> None:
        super().__init__()
        self.tournaments: dict[str, str] = {}
        self._stack: list[tuple[str, set[str]]] = []
        self._phase = ""
        self._heading: list[str] | None = None
        self._link: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag not in {"br", "img", "hr", "input", "meta", "link", "wbr"}:
            self._stack.append((tag, classes))
        if "tournaments-list-heading" in classes:
            self._heading = []
        is_name = any("tournament-name" in classes for _, classes in self._stack)
        is_date = any("tournaments-list-dates" in classes for _, classes in self._stack)
        if tag == "a" and (is_name or is_date):
            title = attributes.get("title")
            if title and ":" not in title and "new" not in classes:
                self._link = {"title": title, "text": [], "is_date": is_date}

    def handle_data(self, data: str) -> None:
        if self._heading is not None:
            self._heading.append(data)
        if self._link is not None:
            self._link["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._link is not None:
            if self._phase in {"Upcoming", "Ongoing"}:
                title = self._link["title"].replace("_", " ")
                name = "".join(self._link["text"]).strip() or title
                if self._link["is_date"]:
                    if title in self.tournaments and name:
                        self.tournaments[title] += f" — {name}"
                else:
                    self.tournaments[title] = f"{name} ({self._phase})"
            self._link = None
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                if "tournaments-list-heading" in self._stack[index][1]:
                    self._phase = "".join(self._heading or []).strip()
                    self._heading = None
                del self._stack[index:]
                break


class LiquipediaAPI:
    """Fetch upcoming matches from a game-specific Liquipedia wiki."""

    _requests_by_loop: WeakKeyDictionary[
        asyncio.AbstractEventLoop, dict[str, _HostRequests]
    ] = WeakKeyDictionary()

    def __init__(self, game: str, session: aiohttp.ClientSession | None = None) -> None:
        """Initialize the API client."""
        self._session = session
        self._owns_session = session is None
        self._game = game
        self._base_url = LIQUIPEDIA_API_URL.format(game=game)
        self._host = urlsplit(self._base_url).netloc

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
        payload = await self._async_parse({"page": page_title})
        page_html = payload["parse"]["text"]["*"]

        parser = _MatchScheduleParser()
        parser.feed(page_html)
        return sorted(
            parser.matches,
            key=lambda match: match["date"],
        )

    async def get_tournaments(self) -> dict[str, str]:
        """Return ongoing tournaments and those starting in the next 30 days.

        Ask the wiki's ticker to filter its tournament database, rather than
        relying on the shorter time window displayed on the main page.
        """
        payload = await self._async_parse({
            "text": (
                "{{#invoke:Widget/Factory|fromTemplate"
                "|widget=Tournaments/Ticker|upcomingDays=30|completedDays=0}}"
            ),
            "contentmodel": "wikitext",
            "title": "Main Page",
        })
        page_html = payload["parse"]["text"]["*"]
        if "tournaments-list" not in page_html:
            raise ValueError("Liquipedia tournament discovery is unavailable")
        parser = _TournamentListParser()
        parser.feed(page_html)
        return parser.tournaments

    async def get_schedule_page(self, tournament: str) -> str:
        """Find an existing schedule page without guessing a subpage title."""
        payload = await self._async_parse({"page": tournament}, prop="text|links")
        tournament = normalize_title(payload["parse"].get("title") or tournament)
        parser = _MatchScheduleParser()
        parser.feed(payload["parse"]["text"]["*"])
        if parser.matches:
            return tournament
        for link in payload["parse"].get("links", []):
            title = link.get("*", "").replace("_", " ")
            if (
                link.get("ns") == 0
                and "exists" in link
                and title.startswith(f"{tournament}/")
                and title.endswith("/Match Schedule")
            ):
                return title
        raise ValueError("No supported match schedule found for this tournament")

    async def search_teams(self, query: str) -> list[str]:
        """Find canonical team pages by title prefix on the selected wiki."""
        if not (query := normalize_title(query)):
            return []
        pages = await self._async_team_pages({
            "generator": "prefixsearch",
            "gpssearch": query,
            "gpsnamespace": "0",
            "gpslimit": "20",
        })
        ranked = sorted(
            pages,
            key=lambda page: index if isinstance(index := page.get("index"), int) else float("inf"),
        )
        return list(dict.fromkeys(page["title"] for page in ranked))

    async def resolve_team(self, title: str) -> str:
        """Resolve an exact or redirected title to a canonical team page."""
        title = normalize_title(title)
        if not title or "|" in title or "#" in title:
            raise TeamNotFoundError("Enter a single Liquipedia team page title")
        pages = await self._async_team_pages({"titles": title})
        if len(pages) != 1:
            raise TeamNotFoundError("No Liquipedia team page was found for this title")
        return pages[0]["title"]

    async def _async_team_pages(self, source: dict[str, str]) -> list[dict[str, Any]]:
        payload = await self._async_request({
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "redirects": "1",
            "prop": "templates",
            "tltemplates": _TEAM_INFOBOX,
            "tllimit": "50",
            **source,
        })
        query = payload.get("query")
        if query is None and payload.get("batchcomplete") is True:
            return []
        if not isinstance(query, dict) or not isinstance(pages := query.get("pages"), list):
            raise ValueError("Liquipedia returned an unexpected team lookup response")
        return [
            page for page in pages
            if isinstance(page, dict)
            and page.get("ns") == 0
            and "missing" not in page
            and "invalid" not in page
            and isinstance(page.get("title"), str)
            and isinstance(page.get("templates"), list)
            and any(
                isinstance(template, dict) and template.get("title") == _TEAM_INFOBOX
                for template in page["templates"]
            )
        ]

    async def get_team_matches(self, team: str) -> list[dict[str, Any]]:
        """Return normalized scheduled or ongoing matches from a team page."""
        payload = await self._async_parse({"page": team})
        parsed = payload["parse"]
        title = parsed.get("title")
        if not isinstance(title, str) or not (title := normalize_title(title)):
            raise ValueError("Liquipedia returned an unexpected team page response")

        return await asyncio.to_thread(
            TeamPageParser.parse_matches, parsed["text"]["*"], title, self._game
        )

    async def _async_parse(
        self, source: dict[str, str], *, prop: str | None = None
    ) -> dict[str, Any]:
        """Share short-lived page results and in-flight requests across clients."""
        if page := source.get("page"):
            # Schedule resolution also needs links. Sharing one representation
            # lets setup, refreshes, and other consumers reuse the same response.
            source = {**source, "page": normalize_title(page), "redirects": "1"}
            prop = prop or "text|links"
        params = {"action": "parse", "format": "json", "prop": prop or "text", **source}
        key = self._base_url, tuple(sorted(params.items()))
        state = self._host_requests()
        loop = asyncio.get_running_loop()
        if cached := state.cache.get(key):
            expires_at, payload = cached
            if loop.time() < expires_at:
                state.cache.move_to_end(key)
                return payload
            del state.cache[key]

        if (pending := state.parses.get(key)) is None:
            task = loop.create_task(self._async_fetch_parse(params, state, key))
            pending = state.parses[key] = _PendingParse(task)

        pending.waiters += 1
        try:
            return await asyncio.shield(pending.task)
        finally:
            pending.waiters -= 1
            if pending.waiters == 0:
                del state.parses[key]
                if not pending.task.done():
                    pending.task.cancel()

    async def _async_fetch_parse(
        self, params: dict[str, str], state: _HostRequests, key: _ParseKey
    ) -> dict[str, Any]:
        await self._async_wait_for_parse_slot()
        payload = await self._async_request(params, rate_limited=True)
        try:
            if not isinstance(payload["parse"]["text"]["*"], str):
                raise ValueError("Liquipedia returned an unexpected API response")
        except (KeyError, TypeError) as error:
            raise ValueError("Liquipedia returned an unexpected API response") from error

        expires_at = asyncio.get_running_loop().time() + _PARSE_CACHE_SECONDS
        state.cache[key] = (expires_at, payload)
        if len(state.cache) > _PARSE_CACHE_SIZE:
            state.cache.popitem(last=False)
        return payload

    async def _async_request(
        self, params: dict[str, str], *, rate_limited: bool = False
    ) -> dict[str, Any]:
        if not rate_limited:
            await self._async_wait_for_request_slot()
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
                timeout=aiohttp.ClientTimeout(total=30),
            )
        async with self._session.get(
            self._base_url,
            params=params,
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            response.raise_for_status()
            payload = await response.json()
        if not isinstance(payload, dict):
            raise ValueError("Liquipedia returned an unexpected API response")
        if error := payload.get("error"):
            if isinstance(error, dict) and isinstance(info := error.get("info"), str):
                raise ValueError(info)
            raise ValueError("Liquipedia reported an API error")
        return payload

    def _host_requests(self) -> _HostRequests:
        hosts = self._requests_by_loop.setdefault(asyncio.get_running_loop(), {})
        if self._host not in hosts:
            hosts[self._host] = _HostRequests()
        return hosts[self._host]

    async def _async_wait_for_request_slot(self) -> None:
        """Space all requests to Liquipedia, including requests across wikis."""
        state = self._host_requests()
        loop = asyncio.get_running_loop()
        async with state.request_lock:
            delay = state.next_request - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            state.next_request = loop.time() + _REQUEST_INTERVAL_SECONDS

    async def _async_wait_for_parse_slot(self) -> None:
        """Respect the host-wide parse cooldown without waiting an unbounded queue."""
        state = self._host_requests()
        loop = asyncio.get_running_loop()
        try:
            async with asyncio.timeout(_MAX_PARSE_WAIT_SECONDS):
                async with state.parse_lock:
                    delay = state.next_parse - loop.time()
                    if delay > 0:
                        await asyncio.sleep(delay)
                    await self._async_wait_for_request_slot()
                    state.next_parse = loop.time() + _PARSE_REQUEST_INTERVAL_SECONDS
        except TimeoutError as error:
            raise TimeoutError("Liquipedia's parse request queue is busy") from error
