"""Standalone test script to demonstrate sensor output."""
import asyncio
import sys
import os
from unittest.mock import MagicMock

# Add the parent directory to the path so we can import the custom component
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from custom_components.liquipedia.sensor import (
    LiquipediaDataUpdateCoordinator,
    LiquipediaTournamentSensor,
    LiquipediaUpcomingMatchesSensor,
)
from custom_components.liquipedia.api import LiquipediaAPI
from custom_components.liquipedia.const import CONF_GAME, CONF_TOURNAMENT


class MockHomeAssistant:
    """Mock Home Assistant instance."""
    pass


class MockConfigEntry:
    """Mock config entry."""
    def __init__(self, entry_id="test_123", game="leagueoflegends", tournament="LCS"):
        self.entry_id = entry_id
        self.data = {
            CONF_GAME: game,
            CONF_TOURNAMENT: tournament,
        }


async def test_sensor_output():
    """Test and display sensor output."""
    print("🚀 Testing Liquipedia Sensors")
    print("=" * 50)

    # Create mock objects
    hass = MockHomeAssistant()
    config_entry = MockConfigEntry(
        entry_id="test_123",
        game="leagueoflegends",
        tournament="LEC Spring 2024"
    )

    print(f"📋 Configuration:")
    print(f"   Game: {config_entry.data[CONF_GAME]}")
    print(f"   Tournament: {config_entry.data[CONF_TOURNAMENT]}")
    print()

    # Test API directly first
    print("🔌 Testing API Connection...")
    try:
        async with LiquipediaAPI(config_entry.data[CONF_GAME]) as api:
            tournament_info = await api.get_tournament_info(config_entry.data[CONF_TOURNAMENT])
            upcoming_matches = await api.get_upcoming_matches(config_entry.data[CONF_TOURNAMENT])

            print("✅ API Response - Tournament Info:")
            for key, value in tournament_info.items():
                print(f"   {key}: {value}")
            print()

            print("✅ API Response - Upcoming Matches:")
            for i, match in enumerate(upcoming_matches, 1):
                print(f"   Match {i}:")
                for key, value in match.items():
                    print(f"     {key}: {value}")
                print()
    except Exception as e:
        print(f"❌ API Error: {e}")
        print()

    # Test coordinator
    print("🎛️  Testing Data Coordinator...")
    coordinator = LiquipediaDataUpdateCoordinator(hass, config_entry)

    try:
        # Manually fetch data to test coordinator
        data = await coordinator._async_update_data()
        coordinator.data = data  # Set the data manually for sensor testing

        print("✅ Coordinator Data:")
        print(f"   Tournament Info: {data.get('tournament_info', 'None')}")
        print(f"   Upcoming Matches Count: {len(data.get('upcoming_matches', []))}")
        print()

        # Test Tournament Sensor
        print("🏆 Testing Tournament Sensor...")
        tournament_sensor = LiquipediaTournamentSensor(coordinator, config_entry)

        print("✅ Tournament Sensor Output:")
        print(f"   Name: {tournament_sensor._attr_name}")
        print(f"   Unique ID: {tournament_sensor._attr_unique_id}")
        print(f"   Native Value: {tournament_sensor.native_value}")
        print(f"   Extra State Attributes:")

        attributes = tournament_sensor.extra_state_attributes
        if attributes:
            for key, value in attributes.items():
                print(f"     {key}: {value}")
        else:
            print("     No attributes available")
        print()

        # Test Matches Sensor
        print("⚔️  Testing Upcoming Matches Sensor...")
        matches_sensor = LiquipediaUpcomingMatchesSensor(coordinator, config_entry)

        print("✅ Matches Sensor Output:")
        print(f"   Name: {matches_sensor._attr_name}")
        print(f"   Unique ID: {matches_sensor._attr_unique_id}")
        print(f"   Native Value: {matches_sensor.native_value}")
        print(f"   Extra State Attributes:")

        attributes = matches_sensor.extra_state_attributes
        if attributes:
            matches = attributes.get("matches", [])
            print(f"     match_count: {len(matches)}")
            for i, match in enumerate(matches, 1):
                print(f"     match_{i}: {match}")
            print(f"     last_updated: {attributes.get('last_updated', 'N/A')}")
        else:
            print("     No attributes available")
        print()

        # Test device info
        print("📱 Device Information:")
        device_info = tournament_sensor.device_info
        for key, value in device_info.items():
            print(f"   {key}: {value}")
        print()

    except Exception as e:
        print(f"❌ Coordinator Error: {e}")
        print()

    print("✨ Test Complete!")


async def test_different_games():
    """Test sensors with different games."""
    print("\n🎮 Testing Different Games")
    print("=" * 30)

    games = ["leagueoflegends", "counterstrike", "dota2", "valorant"]
    tournaments = ["LEC Spring", "IEM Katowice", "The International", "VCT Champions"]

    for game, tournament in zip(games, tournaments):
        print(f"\n🎯 Testing {game.upper()} - {tournament}")
        print("-" * 40)

        config_entry = MockConfigEntry(
            entry_id=f"test_{game}",
            game=game,
            tournament=tournament
        )

        hass = MockHomeAssistant()
        coordinator = LiquipediaDataUpdateCoordinator(hass, config_entry)

        try:
            data = await coordinator._async_update_data()
            coordinator.data = data

            tournament_sensor = LiquipediaTournamentSensor(coordinator, config_entry)
            matches_sensor = LiquipediaUpcomingMatchesSensor(coordinator, config_entry)

            print(f"Tournament: {tournament_sensor.native_value}")
            print(f"Matches: {matches_sensor.native_value}")

            # Show first match if available
            match_attrs = matches_sensor.extra_state_attributes
            if match_attrs and match_attrs.get("matches"):
                first_match = match_attrs["matches"][0]
                print(f"Next Match: {first_match.get('team1', 'TBD')} vs {first_match.get('team2', 'TBD')}")

        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    print("🧪 Liquipedia Sensor Testing Suite")
    print("=" * 50)

    # Run the main test
    asyncio.run(test_sensor_output())

    # Run tests for different games
    asyncio.run(test_different_games())

    print("\n" + "=" * 50)
    print("📊 Testing complete! Use the output above to debug sensor behavior.")
    print("💡 Tip: Run 'python tests/test_sensor_output.py' to see live sensor data.")
