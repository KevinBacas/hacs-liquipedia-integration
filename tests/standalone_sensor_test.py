#!/usr/bin/env python3
"""Standalone sensor test - no external dependencies required."""
import asyncio
import json
from typing import Any, Dict
from datetime import datetime


class MockLiquipediaAPI:
    """Mock version of LiquipediaAPI for testing."""

    def __init__(self, game: str):
        self.game = game
        self._base_url = f"https://liquipedia.net/{game}/api.php"

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def get_tournament_info(self, tournament_name: str = None) -> Dict[str, Any]:
        """Mock tournament information."""
        # Simulate different data based on game
        tournament_data = {
            "leagueoflegends": {
                "name": tournament_name or "LEC Spring 2024",
                "status": "Active",
                "prize_pool": "€200,000",
                "start_date": "2024-01-22",
                "end_date": "2024-03-15",
                "location": "Online",
                "organizer": "Riot Games",
            },
            "counterstrike": {
                "name": tournament_name or "IEM Katowice 2024",
                "status": "Upcoming",
                "prize_pool": "$1,000,000",
                "start_date": "2024-02-05",
                "end_date": "2024-02-11",
                "location": "Katowice, Poland",
                "organizer": "ESL Gaming",
            },
            "dota2": {
                "name": tournament_name or "The International 2024",
                "status": "Planning",
                "prize_pool": "$3,000,000+",
                "start_date": "2024-10-01",
                "end_date": "2024-10-15",
                "location": "TBD",
                "organizer": "Valve Corporation",
            }
        }

        return tournament_data.get(self.game, tournament_data["leagueoflegends"])

    async def get_upcoming_matches(self, tournament_name: str = None) -> list[Dict[str, Any]]:
        """Mock upcoming matches."""
        # Simulate different matches based on game
        match_data = {
            "leagueoflegends": [
                {
                    "team1": "G2 Esports",
                    "team2": "Fnatic",
                    "time": "2024-01-25T18:00:00Z",
                    "format": "Bo1",
                    "tournament": tournament_name or "LEC Spring 2024",
                    "stream": "https://twitch.tv/lec",
                },
                {
                    "team1": "Team BDS",
                    "team2": "MAD Lions KOI",
                    "time": "2024-01-25T19:00:00Z",
                    "format": "Bo1",
                    "tournament": tournament_name or "LEC Spring 2024",
                    "stream": "https://twitch.tv/lec",
                }
            ],
            "counterstrike": [
                {
                    "team1": "NAVI",
                    "team2": "FaZe Clan",
                    "time": "2024-02-06T14:00:00Z",
                    "format": "Bo3",
                    "tournament": tournament_name or "IEM Katowice 2024",
                    "stream": "https://twitch.tv/esl_csgo",
                },
                {
                    "team1": "G2 Esports",
                    "team2": "Vitality",
                    "time": "2024-02-06T17:00:00Z",
                    "format": "Bo3",
                    "tournament": tournament_name or "IEM Katowice 2024",
                    "stream": "https://twitch.tv/esl_csgo",
                }
            ],
            "dota2": [
                {
                    "team1": "Team Spirit",
                    "team2": "PSG.LGD",
                    "time": "2024-10-02T12:00:00Z",
                    "format": "Bo3",
                    "tournament": tournament_name or "The International 2024",
                    "stream": "https://twitch.tv/dota2ti",
                }
            ]
        }

        return match_data.get(self.game, match_data["leagueoflegends"])


class MockCoordinator:
    """Mock coordinator for testing."""

    def __init__(self, game: str, tournament: str = ""):
        self.game = game
        self.tournament = tournament
        self.data = None

    async def update_data(self):
        """Simulate data update."""
        async with MockLiquipediaAPI(self.game) as api:
            self.data = {
                "tournament_info": await api.get_tournament_info(self.tournament),
                "upcoming_matches": await api.get_upcoming_matches(self.tournament),
            }
        return self.data


def simulate_tournament_sensor(coordinator_data: dict, game: str, entry_id: str) -> dict:
    """Simulate tournament sensor output."""
    if not coordinator_data:
        return {"native_value": None, "extra_state_attributes": None}

    tournament_info = coordinator_data.get("tournament_info", {})

    return {
        "name": f"{game.title()} Tournament Info",
        "unique_id": f"{entry_id}_tournament",
        "native_value": tournament_info.get("name", "Unknown"),
        "extra_state_attributes": {
            "status": tournament_info.get("status"),
            "prize_pool": tournament_info.get("prize_pool"),
            "start_date": tournament_info.get("start_date"),
            "end_date": tournament_info.get("end_date"),
            "location": tournament_info.get("location"),
            "organizer": tournament_info.get("organizer"),
            "last_updated": datetime.now().isoformat(),
        }
    }


def simulate_matches_sensor(coordinator_data: dict, game: str, entry_id: str) -> dict:
    """Simulate matches sensor output."""
    if not coordinator_data:
        return {"native_value": None, "extra_state_attributes": None}

    matches = coordinator_data.get("upcoming_matches", [])

    return {
        "name": f"{game.title()} Upcoming Matches",
        "unique_id": f"{entry_id}_matches",
        "native_value": len(matches),
        "extra_state_attributes": {
            "matches": matches,
            "next_match": matches[0] if matches else None,
            "total_matches": len(matches),
            "last_updated": datetime.now().isoformat(),
        }
    }


async def test_sensor_output():
    """Test sensor outputs for different games."""
    print("🧪 Liquipedia Sensor Output Testing")
    print("=" * 50)

    games_tournaments = [
        ("leagueoflegends", "LEC Spring 2024"),
        ("counterstrike", "IEM Katowice 2024"),
        ("dota2", "The International 2024"),
    ]

    for game, tournament in games_tournaments:
        print(f"\n🎮 Testing {game.upper()} - {tournament}")
        print("=" * 60)

        # Simulate coordinator
        coordinator = MockCoordinator(game, tournament)
        await coordinator.update_data()

        print("📊 Raw Coordinator Data:")
        print(json.dumps(coordinator.data, indent=2))

        # Test Tournament Sensor
        print(f"\n🏆 Tournament Sensor Output:")
        tournament_sensor = simulate_tournament_sensor(coordinator.data, game, f"test_{game}")
        print(f"   Name: {tournament_sensor['name']}")
        print(f"   Unique ID: {tournament_sensor['unique_id']}")
        print(f"   Native Value: {tournament_sensor['native_value']}")
        print(f"   Attributes:")
        for key, value in tournament_sensor['extra_state_attributes'].items():
            print(f"     {key}: {value}")

        # Test Matches Sensor
        print(f"\n⚔️  Matches Sensor Output:")
        matches_sensor = simulate_matches_sensor(coordinator.data, game, f"test_{game}")
        print(f"   Name: {matches_sensor['name']}")
        print(f"   Unique ID: {matches_sensor['unique_id']}")
        print(f"   Native Value: {matches_sensor['native_value']}")
        print(f"   Attributes:")
        matches = matches_sensor['extra_state_attributes']['matches']
        print(f"     total_matches: {matches_sensor['extra_state_attributes']['total_matches']}")
        if matches_sensor['extra_state_attributes']['next_match']:
            next_match = matches_sensor['extra_state_attributes']['next_match']
            print(f"     next_match: {next_match['team1']} vs {next_match['team2']} at {next_match['time']}")
        print(f"     last_updated: {matches_sensor['extra_state_attributes']['last_updated']}")

        print("\n" + "-" * 60)


async def test_empty_data():
    """Test sensors with empty data."""
    print("\n🔍 Testing Empty Data Scenarios")
    print("=" * 40)

    # Test with empty coordinator data
    empty_data = {"tournament_info": {}, "upcoming_matches": []}
    tournament_sensor = simulate_tournament_sensor(empty_data, "leagueoflegends", "test_empty")
    matches_sensor = simulate_matches_sensor(empty_data, "leagueoflegends", "test_empty")

    print("📋 Tournament Sensor (Empty Data):")
    print(f"   Native Value: {tournament_sensor['native_value']}")
    print(f"   Attributes: {tournament_sensor['extra_state_attributes']}")

    print("\n⚔️  Matches Sensor (Empty Data):")
    print(f"   Native Value: {matches_sensor['native_value']}")
    print(f"   Total Matches: {matches_sensor['extra_state_attributes']['total_matches']}")

    # Test with None data
    print(f"\n🚫 Testing with None Data:")
    none_tournament = simulate_tournament_sensor(None, "leagueoflegends", "test_none")
    none_matches = simulate_matches_sensor(None, "leagueoflegends", "test_none")

    print(f"   Tournament Native Value: {none_tournament['native_value']}")
    print(f"   Matches Native Value: {none_matches['native_value']}")


async def main():
    """Run all tests."""
    await test_sensor_output()
    await test_empty_data()

    print("\n" + "=" * 50)
    print("✨ Testing Complete!")
    print("\n💡 Key Findings:")
    print("   - Tournament sensor shows tournament name as main value")
    print("   - Matches sensor shows count of upcoming matches")
    print("   - Both sensors provide rich attributes with detailed info")
    print("   - Sensors handle empty/missing data gracefully")
    print("\n🔧 Home Assistant Integration:")
    print("   - Copy this test data format to your actual API")
    print("   - Sensors will appear in HA with these exact values")
    print("   - Use the attributes for automations and dashboards")


if __name__ == "__main__":
    asyncio.run(main())
