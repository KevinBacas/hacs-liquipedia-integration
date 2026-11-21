"""Tests for Liquipedia schedule parsing."""

import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.liquipedia import api as api_module
from custom_components.liquipedia.api import (
    LiquipediaAPI,
    ScheduleNotFoundError,
    _MatchScheduleParser,
    _TournamentListParser,
)


def _parse_match(
    row_attributes: str = "",
    row_classes: str = "",
    stream_markup: str = "",
) -> dict[str, object]:
    parser = _MatchScheduleParser()
    parser.feed(
        f"""
        <tr class="table2__row--body {row_classes}" {row_attributes}>
          <td><span data-timestamp="1786118400"></span></td>
          <td>Grand Final</td>
          <td><a title="Team One"></a></td>
          <td>Bo5</td>
          <td><a title="Team Two"></a></td>
          <td>{stream_markup}</td>
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
    match = _parse_match(
        row_attributes='data-match-status="live"',
        row_classes="match-status--finished",
    )

    assert match["status"] == "finished"


def test_parser_does_not_infer_live_status_from_scheduled_time() -> None:
    """A timestamp without an upstream status remains unknown."""
    match = _parse_match()

    assert match["status"] == "unknown"


def test_parser_does_not_treat_stream_controls_as_a_live_match() -> None:
    match = _parse_match(
        row_attributes='data-status="not-live"',
        stream_markup='<a class="livestream" data-status="live">Watch stream</a>',
    )

    assert match["status"] == "unknown"


_EMPTY_SCHEDULE_HTML = """
<table class="table2&#95;&#95;table sortable"><tbody>
  <tr class="table2&#95;&#95;row--head table2&#95;&#95;row--head-title">
    <th data-sort-type="isoDate">Date</th><th>Round</th>
    <th>Opponent</th><th>Score</th><th>vs. Opponent</th><th></th>
  </tr>
</tbody></table>
"""


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
async def test_discovery_requests_rolling_30_day_window(mock_liquipedia_session):
    session = mock_liquipedia_session(
        AsyncMock(return_value={"parse": {"text": {"*": _TICKER_HTML}}})
    )
    api = LiquipediaAPI("valorant", session)

    assert len(await api.get_tournaments()) == 2
    source = session.get.call_args.kwargs["params"]
    assert "upcomingDays=30" in source["text"]
    assert "completedDays=0" in source["text"]


@pytest.mark.asyncio
async def test_discovery_detects_unsupported_ticker(mock_liquipedia_session):
    session = mock_liquipedia_session(
        AsyncMock(return_value={"parse": {"text": {"*": "Lua error"}}})
    )
    api = LiquipediaAPI("valorant", session)

    with pytest.raises(ValueError):
        await api.get_tournaments()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("extra_links", "requested_page"),
    [
        ([], "Cup/2026/Main Event/Match Schedule"),
        ([{"ns": 0, "*": "Cup/2026/Match Schedule", "exists": ""}], "Cup/2026/Match Schedule"),
    ],
)
async def test_schedule_resolution_validates_the_linked_page_and_uses_its_canonical_title(
    extra_links: list[dict], requested_page: str, mock_liquipedia_session, monkeypatch,
):
    monkeypatch.setattr(api_module, "_REQUEST_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(api_module, "_PARSE_REQUEST_INTERVAL_SECONDS", 0)
    session = mock_liquipedia_session(AsyncMock(side_effect=[
        {"parse": {"text": {"*": ""}, "links": [
            {"ns": 0, "*": "Cup/2026/Missing/Match Schedule"},
            {"ns": 0, "*": "Other Cup/Match Schedule", "exists": ""},
            {"ns": 0, "*": "Cup/2026/Main_Event/Match_Schedule", "exists": ""},
            *extra_links,
        ]}},
        {"parse": {
            "title": "Cup/2026/Match Schedule",
            "text": {"*": _EMPTY_SCHEDULE_HTML},
        }},
    ]))
    api = LiquipediaAPI("valorant", session)

    assert await api.get_schedule_page("Cup/2026") == "Cup/2026/Match Schedule"
    assert [call.kwargs["params"]["page"] for call in session.get.call_args_list] == [
        "Cup/2026", requested_page,
    ]


@pytest.mark.asyncio
async def test_schedule_resolution_rejects_tournament_without_supported_schedule(mock_liquipedia_session):
    session = mock_liquipedia_session(
        AsyncMock(return_value={"parse": {"text": {"*": ""}, "links": []}})
    )
    api = LiquipediaAPI("valorant", session)

    with pytest.raises(ScheduleNotFoundError):
        await api.get_schedule_page("Cup")


@pytest.mark.asyncio
async def test_schedule_resolution_keeps_embedded_match_table(mock_liquipedia_session):
    session = mock_liquipedia_session(AsyncMock(return_value={"parse": {"text": {"*": '''
        <tr class="row--body">
          <td><span data-timestamp="1786118400"></span></td><td>Final</td>
          <td><a title="Team One"></a></td><td>Bo5</td><td><a title="Team Two"></a></td>
        </tr>
    '''}}}))
    api = LiquipediaAPI("valorant", session)

    assert await api.get_schedule_page("Cup") == "Cup"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"error": {"info": "Missing page"}},
    {"parse": {}},
    {"parse": {"text": {"*": None}}},
])
async def test_api_rejects_errors_and_malformed_responses(payload, mock_liquipedia_session):
    session = mock_liquipedia_session(AsyncMock(return_value=payload))
    api = LiquipediaAPI("valorant", session)

    with pytest.raises(ValueError):
        await api.get_matches("Cup")
    assert session.get.call_args.kwargs["params"]["page"] == "Cup"
    assert "User-Agent" in session.get.call_args.kwargs["headers"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "error_type"),
    [
        ({"error": {"code": "missingtitle", "info": "Missing page"}}, ScheduleNotFoundError),
        ({"parse": {"text": {"*": "<table class='table2__table'></table>"}}}, ScheduleNotFoundError),
        (
            {"parse": {"text": {"*": "<strong class='error'>Lua error</strong>"}}},
            ValueError,
        ),
        (
            {"parse": {"text": {"*": _EMPTY_SCHEDULE_HTML.replace(
                "</tbody>", '<tr class="table2__row--body"><td>broken</td></tr></tbody>'
            )}}},
            ValueError,
        ),
    ],
)
async def test_matches_distinguishes_failed_sources_from_a_valid_empty_schedule(
    payload: dict, error_type: type[ValueError], mock_liquipedia_session,
) -> None:
    session = mock_liquipedia_session(AsyncMock(return_value=payload))

    with pytest.raises(error_type) as error:
        await LiquipediaAPI("valorant", session).get_matches("Cup")
    assert type(error.value) is error_type


@pytest.mark.asyncio
async def test_unreadable_row_is_reported_even_when_another_match_is_valid(
    mock_liquipedia_session,
) -> None:
    html = _EMPTY_SCHEDULE_HTML.replace("</tbody>", """
      <tr class="table2__row--body">
        <td><span data-timestamp="1786118400"></span></td><td>Final</td>
        <td><a title="Team One"></a></td><td>Bo5</td><td><a title="Team Two"></a></td>
      </tr>
      <tr class="table2__row--body">
        <td><span data-timestamp="bad"></span></td><td>Semifinal</td>
        <td><a title="Team Three"></a></td><td>Bo5</td><td><a title="Team Four"></a></td>
      </tr>
    </tbody>""")
    session = mock_liquipedia_session(AsyncMock(return_value={"parse": {"text": {"*": html}}}))

    with pytest.raises(ValueError, match="unreadable match schedule"):
        await LiquipediaAPI("valorant", session).get_matches("Cup")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["", 'data-match-status="live"'])
async def test_schedule_distinguishes_unscheduled_placeholders_from_live_rows(
    status: str, mock_liquipedia_session,
) -> None:
    html = _EMPTY_SCHEDULE_HTML.replace("</tbody>", f"""
      <tr class="table2__row--body">
        <td>TBD</td><td>Final</td>
        <td><a title="Team One"></a></td><td>Bo5</td><td><a title="Team Two"></a></td>
      </tr>
      <tr class="table2__row--body" {status}>
        <td><span data-timestamp="1786118400"></span></td><td>Semifinal</td>
        <td><a title="Team Three"></a></td><td>Bo5</td><td>TBD</td>
      </tr>
    </tbody>""")
    session = mock_liquipedia_session(AsyncMock(return_value={"parse": {"text": {"*": html}}}))
    api = LiquipediaAPI("valorant", session)

    if status:
        with pytest.raises(ValueError, match="unreadable match schedule"):
            await api.get_matches("Cup")
    else:
        assert await api.get_matches("Cup") == []


def test_recognized_table_reads_matches_after_a_body_class_change() -> None:
    html = _EMPTY_SCHEDULE_HTML.replace("</tbody>", """
      <tr><th colspan="6">Playoffs</th></tr>
      <tr class="schedule-updated" data-match-status="live">
        <td><span data-timestamp="1786118400"></span></td><td>Final</td>
        <td><a title="Team One"></a></td><td>Bo5</td><td><a title="Team Two"></a></td>
      </tr>
    </tbody>""")

    assert [match["status"] for match in _MatchScheduleParser.parse(html).matches] == ["live"]


@pytest.mark.asyncio
async def test_page_parse_is_shared_by_schedule_resolution_and_updates(mock_liquipedia_session) -> None:
    started = asyncio.Event()
    release_response = asyncio.Event()

    async def read_json() -> dict:
        started.set()
        await release_response.wait()
        return {"parse": {"title": "Official Cup", "text": {"*": _EMPTY_SCHEDULE_HTML}}}

    session = mock_liquipedia_session(AsyncMock(side_effect=read_json))
    first_api = LiquipediaAPI("valorant", session)
    second_api = LiquipediaAPI("valorant", session)
    lookup = asyncio.create_task(first_api.get_schedule_page("Test_Cup"))
    await started.wait()
    update = asyncio.create_task(second_api.get_matches("Test Cup"))
    await asyncio.sleep(0)
    release_response.set()

    assert await lookup == "Official Cup"
    assert await update == []
    assert await second_api.get_matches("Official Cup") == []
    session.get.assert_called_once()
    assert session.get.call_args.kwargs["params"]["redirects"] == "1"


@pytest.mark.asyncio
async def test_cancelling_one_waiter_keeps_shared_fetch_alive(mock_liquipedia_session) -> None:
    started = asyncio.Event()
    release_response = asyncio.Event()

    async def read_json() -> dict:
        started.set()
        await release_response.wait()
        return {"parse": {"text": {"*": _EMPTY_SCHEDULE_HTML}}}

    session = mock_liquipedia_session(AsyncMock(side_effect=read_json))
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
async def test_rate_budget_is_shared_across_four_team_games_and_a_tournament(
    monkeypatch, mock_liquipedia_session,
) -> None:
    assert api_module._MAX_PARSE_WAIT_SECONDS > 5 * api_module._PARSE_REQUEST_INTERVAL_SECONDS
    monkeypatch.setattr(api_module, "_REQUEST_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(api_module, "_PARSE_REQUEST_INTERVAL_SECONDS", 0.04)
    monkeypatch.setattr(api_module, "_MAX_PARSE_WAIT_SECONDS", 0.25)
    session = mock_liquipedia_session(AsyncMock(return_value={
        "parse": {"text": {"*": _EMPTY_SCHEDULE_HTML}}, "batchcomplete": True,
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
async def test_busy_parse_budget_expires_before_another_http_request(
    monkeypatch, mock_liquipedia_session,
) -> None:
    monkeypatch.setattr(api_module, "_MAX_PARSE_WAIT_SECONDS", 0.01)
    session = mock_liquipedia_session(
        AsyncMock(return_value={"parse": {"text": {"*": _EMPTY_SCHEDULE_HTML}}})
    )
    api = LiquipediaAPI("counterstrike", session)

    assert await api.get_matches("First") == []
    with pytest.raises(TimeoutError, match="parse request queue is busy"):
        await api.get_matches("Second")
    session.get.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "retry_after"),
    [
        (429, "60"),
        (503, format_datetime(datetime.now(timezone.utc) + timedelta(minutes=5), usegmt=True)),
    ],
)
async def test_http_retry_after_pauses_queries_and_parses_across_wikis(
    status: int, retry_after: str, mock_liquipedia_session,
) -> None:
    session = mock_liquipedia_session(AsyncMock())
    response = await session.get.return_value.__aenter__()
    response.status = status
    response.headers = {"Retry-After": retry_after}
    response.raise_for_status.side_effect = aiohttp.ClientResponseError(
        MagicMock(), (), status=status,
    )
    first_api = LiquipediaAPI("valorant", session)
    second_api = LiquipediaAPI("counterstrike", session)

    with pytest.raises(aiohttp.ClientResponseError):
        await first_api.search_teams("Team")
    with pytest.raises(TimeoutError, match="Liquipedia requested a pause"):
        await second_api.get_matches("Cup")
    with pytest.raises(TimeoutError, match="Liquipedia requested a pause"):
        await second_api.search_teams("Team")
    session.get.assert_called_once()
