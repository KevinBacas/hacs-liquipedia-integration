"""Tests for Liquipedia schedule parsing."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.liquipedia import api as api_module
from custom_components.liquipedia.api import (
    LiquipediaAPI,
    _MatchScheduleParser,
    _TournamentListParser,
)


def _parse_match(status_markup: str = "") -> dict[str, object]:
    parser = _MatchScheduleParser()
    parser.feed(
        f"""
        <tr class="match-row row--body" {status_markup}>
          <td><span data-timestamp="1786118400"></span></td>
          <td>Grand Final</td>
          <td><a title="Team One"></a></td>
          <td>Bo5</td>
          <td><a title="Team Two"></a></td>
        </tr>
        """
    )
    return parser.matches[0]


def test_parser_marks_explicitly_live_match_as_live() -> None:
    """An explicit live marker is exposed to the binary sensor."""
    match = _parse_match('data-match-status="live"')

    assert match["status"] == "live"


def test_parser_marks_explicitly_finished_match_as_finished() -> None:
    """A completed match must not be treated as live."""
    match = _parse_match('class="match-row row--body match-status--finished"')

    assert match["status"] == "finished"


def test_parser_does_not_infer_live_status_from_scheduled_time() -> None:
    """A timestamp without an upstream status remains unknown."""
    match = _parse_match()

    assert match["status"] == "unknown"


_TICKER_HTML = """
<div class="tournaments-list">
  <span class="tournaments-list-heading">Upcoming</span>
  <ul><li><span class="tournaments-list-name">
    <span class="tournament-icon"><a title="Wrong icon link"></a></span>
    <span class="tournament-name"><a title="Cup/2026">Cup &amp; Friends</a></span>
  </span><small class="tournaments-list-dates"><a title="Cup/2026">Oct 3</a></small></li></ul>
  <span class="tournaments-list-heading">Ongoing</span>
  <ul><li><span class="tournament-name"><a title="League/2026">League</a></span></li></ul>
  <span class="tournaments-list-heading">Completed</span>
  <ul><li><span class="tournament-name"><a title="Old cup">Old cup</a></span></li></ul>
</div>
"""


def test_ticker_parser_ignores_completed_and_non_tournament_links():
    parser = _TournamentListParser()
    parser.feed(_TICKER_HTML)
    assert parser.tournaments == {
        "Cup/2026": "Cup & Friends (Upcoming) — Oct 3", "League/2026": "League (Ongoing)"
    }


@pytest.mark.asyncio
async def test_discovery_requests_rolling_30_day_window():
    api = LiquipediaAPI("valorant")
    api._async_parse = AsyncMock(return_value={"parse": {"text": {"*": _TICKER_HTML}}})
    assert len(await api.get_tournaments()) == 2
    source = api._async_parse.call_args.args[0]
    assert "upcomingDays=30" in source["text"]
    assert "completedDays=0" in source["text"]


@pytest.mark.asyncio
async def test_discovery_detects_unsupported_ticker():
    api = LiquipediaAPI("valorant")
    api._async_parse = AsyncMock(return_value={"parse": {"text": {"*": "Lua error"}}})
    with pytest.raises(ValueError):
        await api.get_tournaments()


@pytest.mark.asyncio
async def test_schedule_resolution_uses_existing_link_not_guessed_title():
    api = LiquipediaAPI("valorant")
    api._async_parse = AsyncMock(return_value={"parse": {"text": {"*": ""}, "links": [
        {"ns": 0, "*": "Cup/2026/Missing/Match Schedule"},
        {"ns": 0, "*": "Other Cup/Match Schedule", "exists": ""},
        {"ns": 0, "*": "Cup/2026/Main_Event/Match_Schedule", "exists": ""},
    ]}})
    assert await api.get_schedule_page("Cup/2026") == "Cup/2026/Main Event/Match Schedule"


@pytest.mark.asyncio
async def test_schedule_resolution_rejects_tournament_without_supported_schedule():
    api = LiquipediaAPI("valorant")
    api._async_parse = AsyncMock(return_value={"parse": {"text": {"*": ""}, "links": []}})
    with pytest.raises(ValueError):
        await api.get_schedule_page("Cup")


@pytest.mark.asyncio
async def test_schedule_resolution_keeps_embedded_match_table():
    api = LiquipediaAPI("valorant")
    api._async_parse = AsyncMock(return_value={"parse": {"text": {"*": '''
        <tr class="row--body">
          <td><span data-timestamp="1786118400"></span></td><td>Final</td>
          <td><a title="Team One"></a></td><td>Bo5</td><td><a title="Team Two"></a></td>
        </tr>
    '''}}})
    assert await api.get_schedule_page("Cup") == "Cup"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"error": {"info": "Missing page"}},
    {"parse": {}},
    {"parse": {"text": {"*": None}}},
])
async def test_api_rejects_errors_and_malformed_responses(payload):
    session = MagicMock()
    response = MagicMock()
    response.json = AsyncMock(return_value=payload)
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    session.get.return_value.__aexit__ = AsyncMock(return_value=False)
    api = LiquipediaAPI("valorant", session)
    api._async_wait_for_parse_slot = AsyncMock()
    with pytest.raises(ValueError):
        await api.get_matches("Cup")
    api._async_wait_for_parse_slot.assert_awaited_once()
    assert session.get.call_args.kwargs["params"]["page"] == "Cup"
    assert "User-Agent" in session.get.call_args.kwargs["headers"]


def _mock_session(read_json: AsyncMock) -> MagicMock:
    session = MagicMock()
    response = MagicMock(json=read_json)
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    session.get.return_value.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.mark.asyncio
async def test_page_parse_is_shared_by_schedule_resolution_and_updates() -> None:
    started = asyncio.Event()
    release_response = asyncio.Event()

    async def read_json() -> dict:
        started.set()
        await release_response.wait()
        return {"parse": {"text": {"*": ""}, "links": [
            {"ns": 0, "*": "Test Cup/Main Event/Match Schedule", "exists": ""},
        ]}}

    session = _mock_session(AsyncMock(side_effect=read_json))
    first_api = LiquipediaAPI("valorant", session)
    second_api = LiquipediaAPI("valorant", session)
    lookup = asyncio.create_task(first_api.get_schedule_page("Test_Cup"))
    await started.wait()
    update = asyncio.create_task(second_api.get_matches("Test Cup"))
    await asyncio.sleep(0)
    release_response.set()

    assert await lookup == "Test Cup/Main Event/Match Schedule"
    assert await update == []
    assert await second_api.get_matches("Test Cup") == []
    session.get.assert_called_once()
    assert session.get.call_args.kwargs["params"]["redirects"] == "1"


@pytest.mark.asyncio
async def test_cancelling_one_waiter_keeps_shared_fetch_alive() -> None:
    started = asyncio.Event()
    release_response = asyncio.Event()

    async def read_json() -> dict:
        started.set()
        await release_response.wait()
        return {"parse": {"text": {"*": ""}}}

    session = _mock_session(AsyncMock(side_effect=read_json))
    api = LiquipediaAPI("valorant", session)
    first_update = asyncio.create_task(api.get_matches("Cup"))
    await started.wait()
    second_update = asyncio.create_task(api.get_matches("Cup"))
    await asyncio.sleep(0)
    first_update.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_update
    release_response.set()

    assert await second_update == []
    session.get.assert_called_once()


@pytest.mark.asyncio
async def test_rate_budget_is_shared_across_four_team_games_and_a_tournament(monkeypatch) -> None:
    assert api_module._MAX_PARSE_WAIT_SECONDS > 5 * api_module._PARSE_REQUEST_INTERVAL_SECONDS
    monkeypatch.setattr(api_module, "_REQUEST_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(api_module, "_PARSE_REQUEST_INTERVAL_SECONDS", 0.04)
    monkeypatch.setattr(api_module, "_MAX_PARSE_WAIT_SECONDS", 0.25)
    session = _mock_session(AsyncMock(return_value={
        "parse": {"text": {"*": ""}}, "batchcomplete": True,
    }))
    http_starts = []

    def start_request(url: str, **kwargs):
        http_starts.append((url, kwargs["params"]["action"], asyncio.get_running_loop().time()))
        return session.get.return_value

    session.get.side_effect = start_request
    cs = LiquipediaAPI("counterstrike", session)
    lol = LiquipediaAPI("leagueoflegends", session)
    rocket_league = LiquipediaAPI("rocketleague", session)
    valorant = LiquipediaAPI("valorant", session)
    # An earlier request has already started the shared parse cooldown.
    assert await cs.get_matches("Previous schedule") == []
    assert await asyncio.gather(
        cs.get_matches("CS team"),
        lol.search_teams("T1"),
        lol.get_matches("LoL team"),
        rocket_league.get_matches("Rocket League team"),
        valorant.get_matches("Valorant team"),
        valorant.get_matches("Tournament"),
    ) == [[], [], [], [], [], []]

    parse_starts = [started for _, action, started in http_starts if action == "parse"]
    assert len(parse_starts) == 6
    assert len({url for url, _, _ in http_starts}) == 4
    assert all(next_start - previous >= 0.039 for previous, next_start in zip(
        parse_starts, parse_starts[1:]
    ))
    all_starts = [started for _, _, started in http_starts]
    assert all(next_start - previous >= 0.009 for previous, next_start in zip(
        all_starts, all_starts[1:]
    ))


@pytest.mark.asyncio
async def test_busy_parse_budget_expires_before_another_http_request(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "_MAX_PARSE_WAIT_SECONDS", 0.01)
    session = _mock_session(AsyncMock(return_value={"parse": {"text": {"*": ""}}}))
    api = LiquipediaAPI("counterstrike", session)

    assert await api.get_matches("First") == []
    with pytest.raises(TimeoutError, match="parse request queue is busy"):
        await api.get_matches("Second")
    session.get.assert_called_once()
