"""Tests for game-dependent tournament setup."""
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.liquipedia.config_flow import ConfigFlow


def _flow():
    flow = ConfigFlow()
    flow.hass = MagicMock()
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    return flow


@pytest.mark.asyncio
async def test_game_then_tournament_stores_resolved_schedule():
    flow = _flow()
    api = MagicMock()
    api.get_tournaments = AsyncMock(return_value={"Cup/2026": "Cup (Upcoming)"})
    api.get_schedule_page = AsyncMock(return_value="Cup/2026/Match Schedule")
    with patch("custom_components.liquipedia.config_flow.async_get_clientsession"), patch(
        "custom_components.liquipedia.config_flow.LiquipediaAPI", return_value=api
    ) as client:
        result = await flow.async_step_user({"name": "My cup", "game": "valorant"})
    assert result["step_id"] == "tournament"
    assert client.call_args.args[0] == "valorant"
    result = await flow.async_step_tournament({"tournament": "Cup/2026"})
    assert result["data"] == {
        "name": "My cup", "game": "valorant", "tournament": "Cup/2026/Match Schedule"
    }
    flow.async_set_unique_id.assert_awaited_once_with("valorant_Cup/2026/Match Schedule")
    flow._abort_if_unique_id_configured.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, aiohttp.ClientError(), ValueError()])
async def test_empty_or_failed_discovery_keeps_manual_setup(failure):
    flow = _flow()
    api = MagicMock()
    api.get_tournaments = AsyncMock(return_value={}, side_effect=failure)
    with patch("custom_components.liquipedia.config_flow.async_get_clientsession"), patch(
        "custom_components.liquipedia.config_flow.LiquipediaAPI", return_value=api
    ):
        result = await flow.async_step_user({"name": "Cup", "game": "dota2"})
    assert result["errors"]["base"] == ("cannot_connect" if failure else "no_tournaments")
    result = await flow.async_step_tournament({"tournament": "manual-entry"})
    assert result["step_id"] == "manual"
    result = await flow.async_step_manual({"tournament": " Cup/Match Schedule "})
    assert result["data"]["tournament"] == "Cup/Match Schedule"


@pytest.mark.asyncio
async def test_invalid_selection_and_missing_schedule_do_not_create_entry():
    flow = _flow()
    flow._tournaments = {"Cup": "Cup"}
    flow._api = MagicMock()
    flow._api.get_schedule_page = AsyncMock(side_effect=ValueError())
    result = await flow.async_step_tournament({"tournament": "Other cup"})
    assert result["errors"] == {"tournament": "invalid_tournament"}
    flow._api.get_schedule_page.assert_not_called()
    result = await flow.async_step_tournament({"tournament": "Cup"})
    assert result["errors"] == {"base": "no_schedule"}
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
        {"value": "manual-entry", "label": "manual"},
    ]
