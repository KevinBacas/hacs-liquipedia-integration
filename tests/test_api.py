"""Test the Liquipedia API."""
import pytest
from unittest.mock import AsyncMock, patch
import aiohttp

from custom_components.liquipedia.api import LiquipediaAPI


@pytest.mark.asyncio
async def test_api_initialization():
    """Test API initialization."""
    api = LiquipediaAPI("leagueoflegends")
    assert api.game == "leagueoflegends"
    assert "leagueoflegends" in api._base_url


@pytest.mark.asyncio
async def test_get_tournament_info():
    """Test getting tournament information."""
    mock_response_data = {
        "query": {
            "search": [
                {"title": "LEC Spring 2024"}
            ]
        }
    }

    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_response_data)
        mock_get.return_value.__aenter__.return_value = mock_response

        api = LiquipediaAPI("leagueoflegends")

        async with api:
            result = await api.get_tournament_info("LEC Spring 2024")

            assert result is not None
            assert "name" in result
            assert result["name"] == "LEC Spring 2024"
            print(f"Tournament info result: {result}")


@pytest.mark.asyncio
async def test_get_upcoming_matches():
    """Test getting upcoming matches."""
    api = LiquipediaAPI("leagueoflegends")

    async with api:
        result = await api.get_upcoming_matches("LEC Spring 2024")

        assert isinstance(result, list)
        assert len(result) >= 0
        if result:
            match = result[0]
            assert "team1" in match
            assert "team2" in match
            assert "time" in match
        print(f"Upcoming matches result: {result}")


@pytest.mark.asyncio
async def test_api_error_handling():
    """Test API error handling."""
    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_get.return_value.__aenter__.return_value = mock_response

        api = LiquipediaAPI("leagueoflegends")

        async with api:
            result = await api.get_tournament_info("NonexistentTournament")
            assert result == {}  # Should return empty dict on error
