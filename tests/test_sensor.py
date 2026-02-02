"""Test the Liquipedia sensors."""
import pytest
from unittest.mock import MagicMock, AsyncMock
from homeassistant.core import HomeAssistant

from custom_components.liquipedia.sensor import (
    LiquipediaDataUpdateCoordinator,
    LiquipediaTournamentSensor,
    LiquipediaUpcomingMatchesSensor,
)


@pytest.mark.asyncio
async def test_coordinator_initialization(hass, config_entry):
    """Test coordinator initialization."""
    coordinator = LiquipediaDataUpdateCoordinator(hass, config_entry)

    assert coordinator.game == "leagueoflegends"
    assert coordinator.tournament == "LEC Spring 2024"
    assert coordinator.name == "Liquipedia leagueoflegends"


@pytest.mark.asyncio
async def test_coordinator_update_data(hass, config_entry, mock_api_data):
    """Test coordinator data update."""
    coordinator = LiquipediaDataUpdateCoordinator(hass, config_entry)

    # Mock the API calls
    with pytest.MockAsyncContext('custom_components.liquipedia.api.LiquipediaAPI') as mock_api:
        mock_api_instance = AsyncMock()
        mock_api_instance.get_tournament_info.return_value = mock_api_data["tournament_info"]
        mock_api_instance.get_upcoming_matches.return_value = mock_api_data["upcoming_matches"]
        mock_api.return_value = mock_api_instance

        result = await coordinator._async_update_data()

        assert "tournament_info" in result
        assert "upcoming_matches" in result
        assert result["tournament_info"]["name"] == "LEC Spring 2024"
        assert len(result["upcoming_matches"]) == 2

        print(f"Coordinator data: {result}")


class TestLiquipediaTournamentSensor:
    """Test tournament sensor."""

    def test_sensor_initialization(self, config_entry):
        """Test sensor initialization."""
        coordinator = MagicMock()
        sensor = LiquipediaTournamentSensor(coordinator, config_entry)

        assert sensor._attr_name == "Leagueoflegends Tournament Info"
        assert sensor._attr_unique_id == "test_entry_id_tournament"
        assert sensor._game == "leagueoflegends"
        assert sensor._tournament == "LEC Spring 2024"

    def test_sensor_native_value(self, config_entry, mock_api_data):
        """Test sensor native value."""
        coordinator = MagicMock()
        coordinator.data = mock_api_data

        sensor = LiquipediaTournamentSensor(coordinator, config_entry)

        assert sensor.native_value == "LEC Spring 2024"
        print(f"Tournament sensor native value: {sensor.native_value}")

    def test_sensor_extra_state_attributes(self, config_entry, mock_api_data):
        """Test sensor extra state attributes."""
        coordinator = MagicMock()
        coordinator.data = mock_api_data

        sensor = LiquipediaTournamentSensor(coordinator, config_entry)
        attributes = sensor.extra_state_attributes

        assert attributes is not None
        assert attributes["status"] == "Active"
        assert attributes["prize_pool"] == "€200,000"
        assert attributes["start_date"] == "2024-01-22"
        assert attributes["end_date"] == "2024-03-15"
        assert "last_updated" in attributes

        print(f"Tournament sensor attributes: {attributes}")

    def test_sensor_no_data(self, config_entry):
        """Test sensor with no data."""
        coordinator = MagicMock()
        coordinator.data = None

        sensor = LiquipediaTournamentSensor(coordinator, config_entry)

        assert sensor.native_value is None
        assert sensor.extra_state_attributes is None


class TestLiquipediaUpcomingMatchesSensor:
    """Test upcoming matches sensor."""

    def test_sensor_initialization(self, config_entry):
        """Test sensor initialization."""
        coordinator = MagicMock()
        sensor = LiquipediaUpcomingMatchesSensor(coordinator, config_entry)

        assert sensor._attr_name == "Leagueoflegends Upcoming Matches"
        assert sensor._attr_unique_id == "test_entry_id_matches"
        assert sensor._game == "leagueoflegends"
        assert sensor._tournament == "LEC Spring 2024"

    def test_sensor_native_value(self, config_entry, mock_api_data):
        """Test sensor native value."""
        coordinator = MagicMock()
        coordinator.data = mock_api_data

        sensor = LiquipediaUpcomingMatchesSensor(coordinator, config_entry)

        assert sensor.native_value == 2  # Number of matches
        print(f"Matches sensor native value: {sensor.native_value}")

    def test_sensor_extra_state_attributes(self, config_entry, mock_api_data):
        """Test sensor extra state attributes."""
        coordinator = MagicMock()
        coordinator.data = mock_api_data

        sensor = LiquipediaUpcomingMatchesSensor(coordinator, config_entry)
        attributes = sensor.extra_state_attributes

        assert attributes is not None
        assert len(attributes["matches"]) == 2
        assert attributes["matches"][0]["team1"] == "G2 Esports"
        assert attributes["matches"][0]["team2"] == "Fnatic"
        assert "last_updated" in attributes

        print(f"Matches sensor attributes: {attributes}")

    def test_sensor_no_data(self, config_entry):
        """Test sensor with no data."""
        coordinator = MagicMock()
        coordinator.data = None

        sensor = LiquipediaUpcomingMatchesSensor(coordinator, config_entry)

        assert sensor.native_value is None
        assert sensor.extra_state_attributes is None


def test_device_info(config_entry):
    """Test device info property."""
    coordinator = MagicMock()
    sensor = LiquipediaTournamentSensor(coordinator, config_entry)

    device_info = sensor.device_info

    assert device_info["name"] == "Liquipedia Leagueoflegends"
    assert device_info["manufacturer"] == "Liquipedia"
    assert device_info["model"] == "Leagueoflegends"
    print(f"Device info: {device_info}")


class MockAsyncContext:
    """Mock async context manager for testing."""

    def __init__(self, target):
        self.target = target
        self.mock = None

    def __enter__(self):
        import unittest.mock
        self.mock = unittest.mock.patch(self.target)
        return self.mock.__enter__()

    def __exit__(self, *args):
        if self.mock:
            self.mock.__exit__(*args)


# Add MockAsyncContext to pytest
pytest.MockAsyncContext = MockAsyncContext
