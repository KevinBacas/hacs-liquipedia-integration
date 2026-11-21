"""Tests for Liquipedia setup and options."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant import config_entries

from custom_components.liquipedia.api import ScheduleNotFoundError, TeamNotFoundError
from custom_components.liquipedia.config_flow import ConfigFlow


def _flow():
    flow = ConfigFlow()
    flow.hass = MagicMock()
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    return flow


def _options_flow(data, options=None):
    entry = SimpleNamespace(data=data, options=options or {})
    flow = ConfigFlow.async_get_options_flow(entry)
    flow.hass = MagicMock()
    flow.handler = "entry-id"
    flow.hass.config_entries.async_get_known_entry.return_value = entry
    return flow


def _field(schema, field):
    return next(marker for marker in schema.schema if marker.schema == field)


@pytest.mark.asyncio
async def test_game_then_tournament_stores_resolved_schedule():
    flow = _flow()
    api = MagicMock()
    api.get_tournaments = AsyncMock(return_value={"Cup/2026": "Cup (Upcoming)"})
    api.get_schedule_page = AsyncMock(return_value="Cup/2026/Match Schedule")
    result = await flow.async_step_user({"mode": "tournament"})
    assert result["step_id"] == "tournament_game"
    api.get_tournaments.assert_not_called()
    with patch("custom_components.liquipedia.config_flow.async_get_clientsession"), patch(
        "custom_components.liquipedia.config_flow.LiquipediaAPI", return_value=api
    ) as client:
        result = await flow.async_step_tournament_game({"game": "valorant"})
    assert result["step_id"] == "tournament"
    assert client.call_args.args[0] == "valorant"
    result = await flow.async_step_tournament({"tournament": "Cup/2026"})
    assert result["title"] == "Cup/2026"
    assert result["data"] == {
        "mode": "tournament",
        "game": "valorant",
        "tournament": "Cup/2026/Match Schedule",
    }
    flow.async_set_unique_id.assert_awaited_once_with("valorant_Cup/2026/Match Schedule")
    flow._abort_if_unique_id_configured.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, aiohttp.ClientError(), ValueError()])
async def test_empty_or_failed_discovery_keeps_manual_setup(failure):
    flow = _flow()
    api = MagicMock()
    api.get_tournaments = AsyncMock(return_value={}, side_effect=failure)
    api.get_schedule_page = AsyncMock(return_value="Cup/Match Schedule")
    with patch("custom_components.liquipedia.config_flow.async_get_clientsession"), patch(
        "custom_components.liquipedia.config_flow.LiquipediaAPI", return_value=api
    ):
        result = await flow.async_step_tournament_game(
            {"game": "dota2", "team_filter": " Team Liquid "}
        )
    assert result["errors"]["base"] == ("cannot_connect" if failure else "no_tournaments")
    result = await flow.async_step_tournament({"tournament": "manual-entry"})
    assert result["step_id"] == "manual"
    result = await flow.async_step_manual({"tournament": "  "})
    assert result["errors"] == {"tournament": "invalid_schedule"}
    result = await flow.async_step_manual({"tournament": " Cup/Match_Schedule "})
    api.get_schedule_page.assert_awaited_once_with("Cup/Match_Schedule")
    assert result["data"]["tournament"] == "Cup/Match Schedule"
    assert result["data"]["team_filter"] == "Team Liquid"


@pytest.mark.asyncio
async def test_invalid_selection_and_missing_schedule_do_not_create_entry():
    flow = _flow()
    flow._tournaments = {"Cup": "Cup"}
    flow._api = MagicMock()
    flow._api.get_schedule_page = AsyncMock(side_effect=ScheduleNotFoundError())
    result = await flow.async_step_tournament({"tournament": "Other cup"})
    assert result["errors"] == {"tournament": "invalid_tournament"}
    flow._api.get_schedule_page.assert_not_called()
    result = await flow.async_step_tournament({"tournament": "Cup"})
    assert result["errors"] == {"base": "no_schedule"}
    flow.async_set_unique_id.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "errors"),
    [
        (ScheduleNotFoundError(), {"tournament": "invalid_schedule"}),
        (aiohttp.ClientError(), {"base": "cannot_connect"}),
        (ValueError(), {"base": "cannot_connect"}),
    ],
)
async def test_manual_schedule_errors_keep_the_entered_title(failure, errors):
    flow = _flow()
    api = SimpleNamespace(
        get_tournaments=AsyncMock(return_value={}),
        get_schedule_page=AsyncMock(side_effect=failure),
    )
    with patch.object(flow, "_api_for_game", return_value=api):
        await flow.async_step_tournament_game({"game": "valorant"})
    await flow.async_step_tournament({"tournament": "manual-entry"})

    result = await flow.async_step_manual({"tournament": "Example Cup"})

    assert result["step_id"] == "manual"
    assert result["errors"] == errors
    assert _field(result["data_schema"], "tournament").description == {
        "suggested_value": "Example Cup"
    }
    flow.async_set_unique_id.assert_not_called()


@pytest.mark.asyncio
async def test_french_labels_and_manual_option_are_available():
    flow = _flow()
    flow.hass.config.language = "fr"
    flow._tournaments = {"Cup": "Cup (Upcoming) — Oct 3", "League": "League (Ongoing)"}
    result = await flow.async_step_tournament()
    select = next(iter(result["data_schema"].schema.values()))
    assert select.config["options"] == [
        {"value": "Cup", "label": "Cup (À venir) — Oct 3"},
        {"value": "League", "label": "League (En cours)"},
        {"value": "manual-entry", "label": "Enter a schedule manually"},
    ]


@pytest.mark.asyncio
async def test_team_name_then_games_and_per_game_confirmation():
    flow = _flow()
    lol = SimpleNamespace(
        search_teams=AsyncMock(return_value=["Team Liquid", "Team Liquid Academy"])
    )
    cs = SimpleNamespace(search_teams=AsyncMock(return_value=["Team Liquid"]))
    rocket_league = SimpleNamespace(search_teams=AsyncMock(return_value=["Team Liquid Rocket League"]))
    valorant = SimpleNamespace(search_teams=AsyncMock(return_value=["Team Liquid Valorant"]))
    apis = {
        "leagueoflegends": lol,
        "counterstrike": cs,
        "rocketleague": rocket_league,
        "valorant": valorant,
    }

    result = await flow.async_step_user()
    mode_field = _field(result["data_schema"], "mode")
    assert result["data_schema"].schema[mode_field].config["options"] == [
        "team", "tournament"
    ]
    result = await flow.async_step_user({"mode": "team"})
    assert result["step_id"] == "team_name"
    result = await flow.async_step_team_name({"team_name": "   "})
    assert result["errors"] == {"team_name": "invalid_team_name"}
    result = await flow.async_step_team_name({"team_name": " Team  Liquid "})
    assert result["step_id"] == "team_games"
    games_field = _field(result["data_schema"], "games")
    games_selector = result["data_schema"].schema[games_field]
    assert games_selector.config["multiple"] is True
    assert [game["value"] for game in games_selector.config["options"]] == list(apis)
    for games in ([], ["dota2"]):
        result = await flow.async_step_team_games({"games": games})
        assert result["errors"] == {"games": "invalid_team_games"}
    for api in apis.values():
        api.search_teams.assert_not_called()

    with patch.object(flow, "_api_for_game", side_effect=apis.__getitem__):
        result = await flow.async_step_team_games({"games": list(apis)})
        assert result["step_id"] == "team_page"
        assert result["last_step"] is False
        assert result["description_placeholders"] == {
            "team_name": "Team Liquid", "game": "League of Legends"
        }
        match_field = _field(result["data_schema"], "team_match")
        assert match_field.description is None
        result = await flow.async_step_team_page({"team_match": "Unknown Team"})
        assert result["errors"] == {"team_match": "invalid_team_page"}
        result = await flow.async_step_team_page({"team_match": "Team Liquid Academy"})
        assert result["description_placeholders"]["game"] == "Counter-Strike"
        match_field = _field(result["data_schema"], "team_match")
        assert match_field.description == {"suggested_value": "Team Liquid"}
        result = await flow.async_step_team_page({"team_match": "Team Liquid"})
        assert result["description_placeholders"]["game"] == "Rocket League"
        assert result["last_step"] is False
        result = await flow.async_step_team_page({"team_match": "Team Liquid Rocket League"})
        assert result["description_placeholders"]["game"] == "Valorant"
        assert result["last_step"] is True
        result = await flow.async_step_team_page({"team_match": "Team Liquid Valorant"})

    for api in apis.values():
        api.search_teams.assert_awaited_once_with("Team Liquid")
    assert result["title"] == "Team Liquid"
    assert result["data"] == {
        "mode": "team",
        "team_name": "Team Liquid",
        "team_pages": {
            "leagueoflegends": "Team Liquid Academy",
            "counterstrike": "Team Liquid",
            "rocketleague": "Team Liquid Rocket League",
            "valorant": "Team Liquid Valorant",
        },
    }
    flow.async_set_unique_id.assert_awaited_once_with("team_team liquid")


@pytest.mark.asyncio
@pytest.mark.parametrize("discovery_failure", [None, aiohttp.ClientError()])
async def test_team_manual_page_resolves_redirect_and_recovers_from_error(discovery_failure):
    flow = _flow()
    api = SimpleNamespace(
        search_teams=AsyncMock(return_value=[], side_effect=discovery_failure),
        resolve_team=AsyncMock(
            side_effect=[TeamNotFoundError(), ValueError(), aiohttp.ClientError(), "Canonical Team"]
        ),
    )
    await flow.async_step_team_name({"team_name": "Different name"})
    with patch.object(flow, "_api_for_game", return_value=api):
        result = await flow.async_step_team_games({"games": ["counterstrike"]})
        assert result["errors"] == (
            {"base": "cannot_search_team"} if discovery_failure else {}
        )
        assert set(result["data_schema"].schema) == {"team_page"}
        result = await flow.async_step_team_page({"team_page": "Wrong page"})
        assert result["errors"] == {"team_page": "invalid_team_page"}
        result = await flow.async_step_team_page({"team_page": "Alias"})
        assert result["errors"] == {"base": "cannot_connect_team"}
        result = await flow.async_step_team_page({"team_page": "Alias"})
        assert result["errors"] == {"base": "cannot_connect_team"}
        result = await flow.async_step_team_page({"team_page": " Alias "})

    api.resolve_team.assert_awaited_with("Alias")
    assert result["data"]["team_pages"] == {"counterstrike": "Canonical Team"}


@pytest.mark.asyncio
async def test_team_options_replace_games_and_use_effective_existing_page():
    flow = _options_flow(
        {
            "mode": "team",
            "team_name": "Team Liquid",
            "team_pages": {"leagueoflegends": "Original name", "counterstrike": "Team Liquid"},
        },
        {"team_pages": {"leagueoflegends": "Team Liquid"}},
    )
    assert isinstance(flow, config_entries.OptionsFlowWithReload)
    result = await flow.async_step_init()
    games_field = _field(result["data_schema"], "games")
    assert games_field.description == {"suggested_value": ["leagueoflegends"]}
    api = SimpleNamespace(
        search_teams=AsyncMock(return_value=["Team Liquid"]),
        resolve_team=AsyncMock(return_value="Team Liquid (organization)"),
    )
    with patch.object(flow, "_api_for_game", return_value=api) as client:
        result = await flow.async_step_team_games({"games": ["leagueoflegends", "counterstrike"]})
        client.assert_not_called()
        match_field = _field(result["data_schema"], "team_match")
        assert match_field.description == {"suggested_value": "Team Liquid"}
        result = await flow.async_step_team_page(
            {"team_match": "Team Liquid", "team_page": "New page"}
        )
        assert result["description_placeholders"]["game"] == "Counter-Strike"
        assert client.call_args.args == ("counterstrike",)
        result = await flow.async_step_team_page({"team_match": "Team Liquid"})

    assert result["data"] == {
        "team_pages": {
            "leagueoflegends": "Team Liquid (organization)", "counterstrike": "Team Liquid"
        },
    }
    api.resolve_team.assert_awaited_once_with("New page")
    api.search_teams.assert_awaited_once_with("Team Liquid")

    result = await flow.async_step_team_games({"games": ["leagueoflegends"]})
    result = await flow.async_step_team_page({"team_match": "Team Liquid"})
    assert result["data"] == {"team_pages": {"leagueoflegends": "Team Liquid"}}


@pytest.mark.asyncio
async def test_legacy_tournament_options_add_and_clear_filter():
    legacy = {"game": "dota2", "tournament": "Cup/Match Schedule", "name": "Cup"}
    flow = _options_flow(legacy)
    result = await flow.async_step_init()
    assert result["step_id"] == "init"
    result = await flow.async_step_init({})
    assert result["data"] == {}
    result = await flow.async_step_init({"team_filter": " Team Liquid "})
    assert result["data"] == {"team_filter": "Team Liquid"}

    flow = _options_flow({**legacy, "mode": "tournament", "team_filter": "Team Liquid"})
    result = await flow.async_step_init()
    filter_field = _field(result["data_schema"], "team_filter")
    assert filter_field.description == {"suggested_value": "Team Liquid"}
    result = await flow.async_step_init({})
    assert result["data"] == {"team_filter": ""}
