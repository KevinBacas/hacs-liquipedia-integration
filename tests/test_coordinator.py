"""Verify both tracking modes and what the two entities report."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.liquipedia.binary_sensor import (
    LiquipediaMatchRunningBinarySensor,
)
from custom_components.liquipedia.coordinator import LiquipediaDataUpdateCoordinator
from custom_components.liquipedia.sensor import LiquipediaUpcomingMatchSensor

LATER = datetime.now(timezone.utc) + timedelta(days=2)
SOONER = LATER - timedelta(days=1)


def _match(date=SOONER, *, status="unknown", side1="Team Liquid", side2="Rival"):
    return {
        "title": f"{side1} vs {side2}",
        "team1": side1,
        "team2": side2,
        "date": date,
        "status": status,
        "tournament": "Example Cup",
        "opponent": side2 if side1 == "Team Liquid" else side1,
    }


def _client(*, matches=(), error=None):
    return MagicMock(
        get_matches=AsyncMock(return_value=list(matches), side_effect=error),
        get_team_matches=AsyncMock(return_value=list(matches), side_effect=error),
    )


def _make_coordinator(clients, *, data=None, options=None):
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "stable-id"
    entry.options = options or {}
    entry.data = data if data is not None else {
        "mode": "team",
        "team_name": "Team Liquid",
        "team_pages": {game: "Team Liquid" for game in clients},
    }
    with (
        patch("custom_components.liquipedia.coordinator.async_get_clientsession"),
        patch(
            "custom_components.liquipedia.coordinator.LiquipediaAPI",
            side_effect=lambda game, session: clients[game],
        ),
    ):
        coordinator = LiquipediaDataUpdateCoordinator(hass, entry)
    return coordinator, entry


@pytest.mark.asyncio
async def test_team_selects_next_game_and_explicit_live_across_all_games():
    league = _client(matches=[_match(LATER)])
    counterstrike = _client(matches=[
        _match(SOONER - timedelta(hours=1), status="finished"),
        _match(SOONER - timedelta(hours=2), status="live", side2="Current Opponent"),
        _match(SOONER, side1="Next Opponent", side2="Team Liquid"),
        _match(SOONER, side1="Team Liquid", side2="Next Opponent"),
    ])
    coordinator, entry = _make_coordinator({"leagueoflegends": league, "counterstrike": counterstrike})
    coordinator.data = await coordinator._async_update_data()
    upcoming = LiquipediaUpcomingMatchSensor(coordinator, entry)
    live = LiquipediaMatchRunningBinarySensor(coordinator, entry)

    league.get_team_matches.assert_awaited_once_with("Team Liquid")
    counterstrike.get_team_matches.assert_awaited_once_with("Team Liquid")
    assert len(coordinator.data.matches) == 4
    assert upcoming.native_value == SOONER
    assert upcoming.extra_state_attributes["game"] == "counterstrike"
    assert upcoming.extra_state_attributes["opponent"] == "Next Opponent"
    assert upcoming.extra_state_attributes["source_url"] == "https://liquipedia.net/counterstrike/Team_Liquid"
    assert live.is_on is True
    assert live.extra_state_attributes["opponent"] == "Current Opponent"


@pytest.mark.asyncio
@pytest.mark.parametrize("live_status, expected", [("unknown", None), ("live", True)])
async def test_partial_failure_keeps_healthy_data_but_prevents_a_false_off(live_status, expected):
    coordinator, entry = _make_coordinator({
        "leagueoflegends": _client(error=TimeoutError()),
        "counterstrike": _client(matches=[_match(status=live_status)]),
    })
    coordinator.data = await coordinator._async_update_data()
    live = LiquipediaMatchRunningBinarySensor(coordinator, entry)

    assert live.is_on is expected
    assert live.extra_state_attributes["data_complete"] is False
    assert live.extra_state_attributes["unavailable_games"] == ["leagueoflegends"]


@pytest.mark.asyncio
async def test_distinguishes_no_published_match_from_total_failure():
    empty, entry = _make_coordinator({"leagueoflegends": _client()})
    empty.data = await empty._async_update_data()
    assert LiquipediaUpcomingMatchSensor(empty, entry).native_value is None
    assert LiquipediaMatchRunningBinarySensor(empty, entry).is_on is False

    failed, _ = _make_coordinator({"leagueoflegends": _client(error=ValueError("Changed layout"))})
    with pytest.raises(UpdateFailed, match="leagueoflegends"):
        await failed._async_update_data()


@pytest.mark.asyncio
async def test_finished_duplicate_overrides_live_match():
    client = _client(matches=[_match(status="finished"), _match(status="live")])
    coordinator, entry = _make_coordinator({"counterstrike": client})
    coordinator.data = await coordinator._async_update_data()

    assert len(coordinator.data.matches) == 1
    assert LiquipediaUpcomingMatchSensor(coordinator, entry).native_value is None
    assert LiquipediaMatchRunningBinarySensor(coordinator, entry).is_on is False


@pytest.mark.asyncio
@pytest.mark.parametrize("options, expected", [({}, True), ({"team_filter": " TEAM_LIQUID "}, False)])
async def test_existing_tournament_keeps_entities_and_optional_filter_applies_to_both(options, expected):
    client = _client(matches=[
        _match(SOONER, status="live", side1="Random Team"),
        _match(SOONER, status="finished"),
        _match(LATER, side1="Opponent", side2="Team Liquid"),
    ])
    coordinator, entry = _make_coordinator(
        {"valorant": client}, data={"game": "valorant", "tournament": "Cup"}, options=options
    )
    coordinator.data = await coordinator._async_update_data()
    upcoming = LiquipediaUpcomingMatchSensor(coordinator, entry)
    live = LiquipediaMatchRunningBinarySensor(coordinator, entry)

    client.get_matches.assert_awaited_once_with("Cup")
    client.get_team_matches.assert_not_awaited()
    assert upcoming.unique_id == "stable-id_upcoming_match"
    assert live.unique_id == "stable-id_match_running"
    assert upcoming.native_value == LATER
    assert live.is_on is expected


@pytest.mark.asyncio
async def test_team_options_replace_the_configured_games():
    client = _client()
    coordinator, _ = _make_coordinator(
        {"counterstrike": client},
        data={"mode": "team", "team_name": "Liquid", "team_pages": {"leagueoflegends": "Team Liquid"}},
        options={"team_pages": {"counterstrike": "Team Liquid"}},
    )
    await coordinator._async_update_data()
    client.get_team_matches.assert_awaited_once_with("Team Liquid")
