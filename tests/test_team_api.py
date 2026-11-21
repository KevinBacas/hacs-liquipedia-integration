"""Tests of Liquipedia team discovery and match cards."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from custom_components.liquipedia.api import LiquipediaAPI, TeamNotFoundError


def _team_html(content: str = "", extra: str = "") -> str:
    return f"""
      <div class="fo-nttax-infobox-container" data-analytics-infobox-type="Team">
        <div class="fo-nttax-infobox-topcontent">{content}</div>
      </div>{extra}
    """


def _team_ticker(cards: str) -> str:
    return f"""
      <div><div>
        <div class="mw-heading mw-heading2"><h2 id="Upcoming_Matches">Upcoming Matches</h2></div>
        <div class="match-ticker-carousel">{cards}</div>
      </div></div>
    """


def _match_card(timestamp: str, stream_cta: str = "Watch here", attributes: str = "") -> str:
    return f"""
      <div class="match-ticker-card" {attributes}>
        <div class="match-ticker-card&#95;&#95;header">
          <span class="match-info-countdown">
            <span class="timer-object" data-timestamp="{timestamp}">Nov 22 - 14:00</span>
          </span>
          <div>High (1-0) - Bo3</div>
        </div>
        <div class="match-ticker-card&#95;&#95;opponents">
          <div class="match-ticker-card&#95;&#95;opponent">
            <div class="block-team">
              <span class="team-template-image-icon">
                <a title="WLGaming Esports"><img alt="" /></a>
              </span>
              <span class="name team-name-dynamic">
                <a class="mw-selflink selflink">
                  <div class="team-shortname">WLG</div>
                  <div class="team-name">WLGaming Esports</div>
                </a>
              </span>
            </div>
          </div>
          <div class="match-ticker-card&#95;&#95;opponent">
            <div class="block-team">
              <span class="name team-name-dynamic">
                <a class="new" title="Zena Esports (page does not exist)">
                  <div class="team-shortname">ZENA</div>
                  <div class="team-name">Zena Esports</div>
                </a>
              </span>
            </div>
          </div>
        </div>
        <div class="match-ticker-card-tournament tournament-highlighted-bg">
          <span class="league-icon-small-image">
            <a title="Ignored logo title"><img alt="" /></a>
          </span>
          <span class="match-ticker-card-tournament-name">
            <a title="Legends Premier League/Season 5/Swiss Stage#High (1-0)">
              Legends Premier League Season 5
            </a>
          </span>
        </div>
        <div class="match-info-links">
          <a class="livestream"><span class="match-button-cta-text">{stream_cta}</span></a>
        </div>
      </div>
    """


@pytest.fixture
def team_api(mock_liquipedia_session):
    def make_client(html: str) -> LiquipediaAPI:
        session = mock_liquipedia_session(AsyncMock(return_value={
            "parse": {"title": "WLGaming Esports", "text": {"*": html}},
        }))
        return LiquipediaAPI("leagueoflegends", session)

    return make_client


@pytest.mark.asyncio
async def test_team_cards_use_source_timezone_status_and_competition(team_api) -> None:
    api = team_api(
        _team_html(_team_ticker(_match_card("1795352400") + _match_card("1795266000", "Watch now")))
    )

    live, scheduled = await api.get_team_matches("We Love Gaming")

    assert live["status"] == "live"
    assert scheduled == {
        "date": datetime.fromtimestamp(1795352400, timezone.utc),
        "title": "WLGaming Esports vs Zena Esports",
        "team1": "WLGaming Esports",
        "team2": "Zena Esports",
        "opponent": "Zena Esports",
        "status": "unknown",
        "tournament": "Legends Premier League Season 5",
        "tournament_page": "Legends Premier League/Season 5/Swiss Stage",
        "game": "leagueoflegends",
        "best_of": "BO3",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(("markup", "expected_status"), [
    ('data-match-status="ongoing"', "live"),
    ('data-match-status="cancelled"', "finished"),
    ('data-match-status="livestream"', "unknown"),
    ('data-match-status="not-live"', "unknown"),
])
async def test_team_status_requires_an_explicit_state(
    markup: str, expected_status: str, team_api,
) -> None:
    api = team_api(_team_html(_team_ticker(_match_card("1795352400", attributes=markup))))

    assert (await api.get_team_matches("WLGaming Esports"))[0]["status"] == expected_status


@pytest.mark.asyncio
async def test_team_without_ticker_is_a_valid_empty_schedule(team_api) -> None:
    api = team_api(_team_html(extra='<h2 id="Player_Roster">Player Roster</h2>'))

    assert await api.get_team_matches("WLGaming Esports") == []


@pytest.mark.asyncio
async def test_truncated_team_infobox_is_unavailable(team_api) -> None:
    api = team_api(
        '<div data-analytics-infobox-type="Team"><div class="fo-nttax-infobox-topcontent">'
    )

    with pytest.raises(ValueError, match="supported team page"):
        await api.get_team_matches("WLGaming Esports")


@pytest.mark.asyncio
@pytest.mark.parametrize("with_team_ticker", [False, True])
async def test_unrelated_tickers_cannot_supply_team_matches(with_team_ticker, team_api) -> None:
    unrelated_ticker = _team_ticker(_match_card("1795266000", "Watch now"))
    team_ticker = _team_ticker(_match_card("1795352400")) if with_team_ticker else ""
    api = team_api(_team_html(team_ticker, extra=unrelated_ticker))

    assert [match["status"] for match in await api.get_team_matches("WLGaming Esports")] == (
        ["unknown"] if with_team_ticker else []
    )


@pytest.mark.asyncio
async def test_team_ticker_does_not_attribute_unrelated_cards_to_selected_team(team_api) -> None:
    unrelated_card = (
        _match_card("1795266000", "Watch now")
        .replace("WLGaming Esports", "Another Team")
        .replace('class="mw-selflink selflink"', 'title="Another Team"')
    )
    api = team_api(_team_html(_team_ticker(_match_card("1795352400") + unrelated_card)))

    assert [match["status"] for match in await api.get_team_matches("WLGaming Esports")] == ["unknown"]


@pytest.mark.asyncio
async def test_team_card_accepts_canonical_name_linked_to_a_team_alias(team_api) -> None:
    card = (
        _match_card("1795352400")
        .replace('title="WLGaming Esports"', 'title="We Love Gaming"')
        .replace('class="mw-selflink selflink"', 'title="We Love Gaming"')
    )
    api = team_api(_team_html(_team_ticker(card)))

    (match,) = await api.get_team_matches("We Love Gaming")

    assert match["opponent"] == "Zena Esports"


@pytest.mark.asyncio
@pytest.mark.parametrize("html", [
    '<div data-analytics-infobox-type="Tournament"></div>',
    '<div data-analytics-infobox-type="Team"><div class="unrecognized-content"></div></div>',
    _team_html(_team_ticker("")),
    _team_html(_team_ticker('<div class="match-ticker-card">')),
    _team_html(_team_ticker(_match_card("unparseable"))),
    _team_html('<strong class="error">Lua error</strong>'),
])
async def test_missing_team_or_broken_ticker_raises_source_error(html: str, team_api) -> None:
    with pytest.raises(ValueError):
        await team_api(html).get_team_matches("WLGaming Esports")


def _team_page(title: str, index: int = 1) -> dict:
    return {
        "ns": 0,
        "title": title,
        "index": index,
        "templates": [{"ns": 10, "title": "Template:Infobox team"}],
    }


@pytest.mark.asyncio
async def test_search_returns_ranked_canonical_team_pages_only(mock_liquipedia_session) -> None:
    session = mock_liquipedia_session(AsyncMock(return_value={"query": {"pages": [
        _team_page("Karmine Corp Blue", index=2),
        {"ns": 0, "index": 3, "title": "Karmine Corp/KCX5"},
        _team_page("Karmine Corp", index=1),
    ]}}))
    api = LiquipediaAPI("leagueoflegends", session)

    assert await api.search_teams(" Karmine ") == ["Karmine Corp", "Karmine Corp Blue"]
    params = session.get.call_args.kwargs["params"]
    assert params["action"] == "query"
    assert params["generator"] == "prefixsearch"
    assert params["gpssearch"] == "Karmine"
    assert params["redirects"] == "1"
    assert params["tltemplates"] == "Template:Infobox team"


@pytest.mark.asyncio
async def test_resolve_team_returns_canonical_title_after_redirect(mock_liquipedia_session) -> None:
    session = mock_liquipedia_session(AsyncMock(return_value={"query": {
        "pages": [_team_page("T1")],
        "redirects": [{"from": "SK Telecom T1", "to": "T1"}],
    }}))
    api = LiquipediaAPI("leagueoflegends", session)

    assert await api.resolve_team("SK_Telecom_T1") == "T1"
    assert session.get.call_args.kwargs["params"]["titles"] == "SK Telecom T1"


@pytest.mark.asyncio
@pytest.mark.parametrize("page", [
    {"ns": 0, "title": "Unknown team", "missing": True},
    {"ns": 0, "title": "Cup 2026"},
    {"ns": 10, "title": "Template:Team"},
])
async def test_resolve_team_rejects_missing_and_non_team_pages(page: dict, mock_liquipedia_session) -> None:
    session = mock_liquipedia_session(AsyncMock(return_value={"query": {"pages": [page]}}))
    api = LiquipediaAPI("counterstrike", session)

    with pytest.raises(TeamNotFoundError):
        await api.resolve_team(page["title"])


@pytest.mark.asyncio
async def test_search_returns_empty_for_a_well_formed_empty_response(mock_liquipedia_session) -> None:
    session = mock_liquipedia_session(AsyncMock(return_value={"batchcomplete": True}))

    assert await LiquipediaAPI("leagueoflegends", session).search_teams("Unknown team") == []


@pytest.mark.asyncio
async def test_search_rejects_a_malformed_response(mock_liquipedia_session) -> None:
    session = mock_liquipedia_session(AsyncMock(return_value={}))

    with pytest.raises(ValueError, match="unexpected team lookup response"):
        await LiquipediaAPI("leagueoflegends", session).search_teams("T1")
