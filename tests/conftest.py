"""Test configuration and fixtures."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from custom_components.liquipedia.const import DOMAIN, CONF_GAME, CONF_TOURNAMENT


@pytest.fixture
def hass():
    """Mock HomeAssistant instance."""
    return MagicMock(spec=HomeAssistant)


@pytest.fixture
def config_entry():
    """Mock config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = {
        CONF_GAME: "leagueoflegends",
        CONF_TOURNAMENT: "LEC Spring 2024"
    }
    return entry


@pytest.fixture
def mock_api_data():
    """Mock API response data."""
    return {
        "tournament_info": {
            "name": "LEC Spring 2024",
            "status": "Active",
            "prize_pool": "€200,000",
            "start_date": "2024-01-22",
            "end_date": "2024-03-15",
        },
        "upcoming_matches": [
            {
                "team1": "G2 Esports",
                "team2": "Fnatic",
                "time": "2024-01-25T18:00:00Z",
                "format": "Bo1",
                "tournament": "LEC Spring 2024",
            },
            {
                "team1": "Team BDS",
                "team2": "MAD Lions KOI",
                "time": "2024-01-25T19:00:00Z",
                "format": "Bo1",
                "tournament": "LEC Spring 2024",
            }
        ]
    }
