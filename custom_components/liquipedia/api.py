"""Client for Liquipedia's MediaWiki API."""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from math import isfinite
from typing import Any
from urllib.parse import urlsplit
from weakref import WeakKeyDictionary

import aiohttp

from .const import LIQUIPEDIA_API_URL, USER_AGENT
from .team_parser import (
    BEST_OF_PATTERN,
    TeamPageParser,
    match_status,
    match_status_markers,
    normalize_title,
)

_PARSE_REQUEST_INTERVAL_SECONDS = 30
_REQUEST_INTERVAL_SECONDS = 2
# Allow a cooldown already in progress, four team pages and one tournament.
_MAX_PARSE_WAIT_SECONDS = 155
_PARSE_CACHE_SECONDS = 120
_PARSE_CACHE_SIZE = 32
_TEAM_INFOBOX = "Template:Infobox team"
_UNSCHEDULED_VALUES = {"", "-", "—", "tbd", "tba"}

_ParseKey = tuple[str, tuple[tuple[str, str], ...]]


class TeamNotFoundError(ValueError):
    """The supplied title does not identify a team on the game wiki."""


class ScheduleNotFoundError(ValueError):
    """The supplied title does not identify a supported match schedule."""


class _PageNotFoundError(ValueError):
    """MediaWiki reported that the requested page does not exist."""


@dataclass
class _PendingParse:
    task: asyncio.Task[dict[str, Any]]
    waiters: int = 0


@dataclass
class _HostRequests:
    next_request: float = 0
    next_parse: float = 0
    retry_after: float = 0
    request_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    parse_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    parses: dict[_ParseKey, _PendingParse] = field(default_factory=dict)
    cache: OrderedDict[_ParseKey, tuple[float, dict[str, Any]]] = field(
        default_factory=OrderedDict,
    )


@dataclass
class _ScheduleCell:
    links: list[str] = field(default_factory=list)
    fragments: list[str] = field(default_factory=list)
    timestamp: str | None = None

    @property
    def text(self) -> str:
        return " ".join(self.fragments)


class _MatchScheduleParser(HTMLParser):
    """Extract match rows from Liquipedia's parsed Match_schedule output."""

    def __init__(self) -> None:
        """Initialize the schedule parser."""
        super().__init__()
        self.matches: list[dict[str, Any]] = []
        self.has_schedule_header = False
        self.has_error = False
        self.has_unreadable_rows = False
        self._schedule_table_depth: int | None = None
        self._table_depth = 0
        self._row_table_depth = 0
        self._row: list[_ScheduleCell] | None = None
        self._is_header = False
        self._is_body = False
        self._has_data_cells = False
        self._row_status_values: set[str] = set()
        self._cell: _ScheduleCell | None = None

    @classmethod
    def parse(cls, page_html: str) -> _MatchScheduleParser:
        """Parse a schedule and distinguish malformed markup from an empty table."""
        parser = cls()
        parser.feed(page_html)
        parser.close()
        if parser._row is not None and parser._row_table_depth == parser._schedule_table_depth:
            parser.has_unreadable_rows = True
        if parser.has_unreadable_rows or (parser.has_error and not parser.matches):
            raise ValueError("Liquipedia returned an unreadable match schedule")
        return parser

    @property
    def has_schedule(self) -> bool:
        return bool(self.matches) or self.has_schedule_header

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        """Track cells and their timestamp and team links."""
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if "error" in classes:
            self.has_error = True
        if tag == "table":
            self._table_depth += 1
        if tag == "tr" and self._row is None:
            self._is_header = bool(classes & {"table2__row--head-title", "row--head-title"})
            self._is_body = bool(classes & {"row--body", "table2__row--body"})
            if self._is_header or self._is_body or self._table_depth == self._schedule_table_depth:
                self._row = []
                self._has_data_cells = False
                self._row_table_depth = self._table_depth
                self._row_status_values = match_status_markers(attributes)
            return
        if self._row is None or self._table_depth != self._row_table_depth:
            return
        if tag in {"td", "th"}:
            self._cell = _ScheduleCell()
            self._row.append(self._cell)
            self._has_data_cells |= tag == "td"
        if self._cell is not None and len(self._row) == 1:
            if timestamp := attributes.get("data-timestamp"):
                self._cell.timestamp = timestamp
            if tag == "td" or timestamp or "timer-object" in classes:
                self._row_status_values.update(match_status_markers(attributes))
        if self._cell is not None and tag == "a":
            title = attributes.get("title")
            if title and not title.startswith("Match:"):
                self._cell.links.append(title.removesuffix(" (page does not exist)"))

    def handle_endtag(self, tag: str) -> None:
        """Finish collecting a cell or a match row."""
        if tag == "table":
            if self._table_depth == self._schedule_table_depth:
                self.has_unreadable_rows |= self._row_table_depth == self._table_depth and self._row is not None
                self._schedule_table_depth = None
            self._table_depth = max(0, self._table_depth - 1)
            return
        if self._row is None or self._table_depth != self._row_table_depth:
            return
        if tag in {"td", "th"}:
            self._cell = None
        elif tag == "tr":
            if self._is_header:
                if self._is_schedule_header(self._row):
                    self._schedule_table_depth = self._table_depth
                    self.has_schedule_header = True
            elif (match := self._build_match(self._row, self._row_status_values)) is not None:
                self.matches.append(match)
            elif self._table_depth == self._schedule_table_depth:
                is_live = match_status(self._row_status_values) == "live"
                if is_live or self._is_body or (self._has_data_cells and len(self._row) >= 5):
                    self.has_unreadable_rows |= is_live or not self._is_unscheduled(self._row)
            self._row = None
            self._cell = None

    def handle_data(self, data: str) -> None:
        """Collect visible cell text."""
        if self._cell is not None and self._table_depth == self._row_table_depth and data.strip():
            self._cell.fragments.append(data.strip())

    @staticmethod
    def _is_schedule_header(row: list[_ScheduleCell]) -> bool:
        """Identify the header of a Match Schedule table."""
        headings = [cell.text.casefold().replace(".", "") for cell in row]
        return (
            len(headings) >= 5
            and headings[0] == "date"
            and headings[2] in {"opponent", "team", "player"}
            and headings[3] == "score"
            and headings[4].removeprefix("vs ") == headings[2]
        )

    @staticmethod
    def _is_unscheduled(row: list[_ScheduleCell]) -> bool:
        """Recognize rows that still lack a date or participant."""
        if len(row) < 5:
            return False
        date, _, team1, _, team2 = row[:5]
        if not date.timestamp and date.text.casefold() in _UNSCHEDULED_VALUES:
            return True
        return any(
            not team.links and team.text.casefold() in _UNSCHEDULED_VALUES
            for team in (team1, team2)
        )

    @staticmethod
    def _build_match(
        row: list[_ScheduleCell],
        status_values: set[str],
    ) -> dict[str, Any] | None:
        """Normalize one match-schedule table row."""
        if len(row) < 5:
            return None

        timestamp = row[0].timestamp
        team1 = next(iter(row[2].links), None)
        team2 = next(iter(row[4].links), None)
        if timestamp is None or team1 is None or team2 is None:
            return None

        try:
            date = datetime.fromtimestamp(int(timestamp), timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None

        title = row[1].text
        format_text = row[3].text
        return {
            "title": title or f"{team1} vs {team2}",
            "team1": team1,
            "team2": team2,
            "date": date,
            "status": match_status(status_values),
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
        self.has_ticker = False
        self.has_error = False
        self._stack: list[tuple[str, set[str]]] = []
        self._phase = ""
        self._heading: list[str] | None = None
        self._link: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        self.has_ticker |= "tournaments-list" in classes
        self.has_error |= "error" in classes
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
        _, parser = await self._async_read_schedule(page_title)
        if not parser.has_schedule:
            raise ScheduleNotFoundError("No supported match schedule found on this page")
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
        parser = _TournamentListParser()
        await asyncio.to_thread(parser.feed, payload["parse"]["text"]["*"])
        if not parser.has_ticker or parser.has_error:
            raise ValueError("Liquipedia tournament discovery is unavailable")
        return parser.tournaments

    async def get_schedule_page(self, tournament: str) -> str:
        """Validate a direct or linked match schedule and return its wiki title."""
        parsed, parser = await self._async_read_schedule(tournament)
        tournament = normalize_title(parsed.get("title") or tournament)
        if parser.has_schedule:
            return tournament
        links = parsed.get("links", [])
        if not isinstance(links, list):
            raise ValueError("Liquipedia returned an unexpected list of schedule links")
        candidate = None
        for link in links:
            if (
                isinstance(link, dict)
                and link.get("ns") == 0
                and "exists" in link
                and isinstance(raw_title := link.get("*"), str)
                and (title := normalize_title(raw_title))
                and title.startswith(f"{tournament}/")
                and title.endswith("/Match Schedule")
            ):
                if title == f"{tournament}/Match Schedule":
                    candidate = title
                    break
                candidate = candidate or title
        if candidate is not None:
            linked, linked_parser = await self._async_read_schedule(candidate)
            if linked_parser.has_schedule:
                return normalize_title(linked.get("title") or candidate)
        raise ScheduleNotFoundError("No supported match schedule found for this tournament")

    async def _async_read_schedule(
        self, page_title: str
    ) -> tuple[dict[str, Any], _MatchScheduleParser]:
        try:
            payload = await self._async_parse({"page": page_title})
        except _PageNotFoundError as error:
            raise ScheduleNotFoundError(str(error)) from error
        parsed = payload["parse"]
        parser = await asyncio.to_thread(_MatchScheduleParser.parse, parsed["text"]["*"])
        return parsed, parser

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

    async def _async_parse(self, source: dict[str, str]) -> dict[str, Any]:
        """Share short-lived page results and in-flight requests across clients."""
        prop = "text"
        if page := source.get("page"):
            # Schedule resolution also needs links. Sharing one representation
            # lets setup, refreshes, and other consumers reuse the same response.
            source = {**source, "page": normalize_title(page), "redirects": "1"}
            prop = "text|links"
        params = {"action": "parse", "format": "json", "prop": prop, **source}
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
            parsed = payload["parse"]
            html = parsed["text"]["*"]
            canonical = parsed.get("title")
        except (AttributeError, KeyError, TypeError) as error:
            raise ValueError("Liquipedia returned an unexpected API response") from error
        if not isinstance(html, str) or (canonical is not None and not isinstance(canonical, str)):
            raise ValueError("Liquipedia returned an unexpected API response")

        expires_at = asyncio.get_running_loop().time() + _PARSE_CACHE_SECONDS
        if "page" in params and canonical and (title := normalize_title(canonical)):
            canonical_params = {**params, "page": title}
            canonical_key = self._base_url, tuple(sorted(canonical_params.items()))
            state.cache[canonical_key] = (expires_at, payload)
            state.cache.move_to_end(canonical_key)
        state.cache[key] = (expires_at, payload)
        state.cache.move_to_end(key)
        while len(state.cache) > _PARSE_CACHE_SIZE:
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
            if response.status in {429, 503} and (retry_after := response.headers.get("Retry-After")):
                self._apply_retry_after(retry_after)
            response.raise_for_status()
            payload = await response.json()
        if not isinstance(payload, dict):
            raise ValueError("Liquipedia returned an unexpected API response")
        if error := payload.get("error"):
            if isinstance(error, dict) and isinstance(info := error.get("info"), str):
                if "page" in params and error.get("code") in (
                    "missingtitle",
                    "invalidtitle",
                    "pagecannotexist",
                ):
                    raise _PageNotFoundError(info)
                raise ValueError(info)
            raise ValueError("Liquipedia reported an API error")
        return payload

    def _apply_retry_after(self, header: str) -> None:
        """Pause requests across the host when the upstream server requests it."""
        try:
            if header.isdecimal():
                delay = float(header)
            else:
                retry_at = parsedate_to_datetime(header)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                delay = retry_at.timestamp() - datetime.now(timezone.utc).timestamp()
        except (TypeError, ValueError, OverflowError, OSError):
            return
        if delay > 0 and isfinite(delay):
            state = self._host_requests()
            state.retry_after = max(state.retry_after, asyncio.get_running_loop().time() + delay)

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
            if delay > 0 and state.retry_after <= loop.time():
                await asyncio.sleep(delay)
            if state.retry_after > loop.time():
                raise TimeoutError("Liquipedia requested a pause before further requests")
            state.next_request = loop.time() + _REQUEST_INTERVAL_SECONDS

    async def _async_wait_for_parse_slot(self) -> None:
        """Respect the host-wide parse cooldown without waiting an unbounded queue."""
        state = self._host_requests()
        loop = asyncio.get_running_loop()
        if state.retry_after > loop.time():
            raise TimeoutError("Liquipedia requested a pause before further requests")
        try:
            async with asyncio.timeout(_MAX_PARSE_WAIT_SECONDS):
                async with state.parse_lock:
                    delay = state.next_parse - loop.time()
                    if delay > 0:
                        await asyncio.sleep(delay)
                    await self._async_wait_for_request_slot()
                    state.next_parse = loop.time() + _PARSE_REQUEST_INTERVAL_SECONDS
        except TimeoutError as error:
            if state.retry_after > loop.time():
                raise TimeoutError("Liquipedia requested a pause before further requests") from error
            raise TimeoutError("Liquipedia's parse request queue is busy") from error
