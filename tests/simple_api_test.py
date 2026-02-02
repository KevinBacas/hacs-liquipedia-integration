"""Simple API test without Home Assistant dependencies."""
import asyncio
import sys
import os

# Add the parent directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from custom_components.liquipedia.api import LiquipediaAPI


async def test_api_simple():
    """Simple test of the Liquipedia API."""
    print("🚀 Testing Liquipedia API")
    print("=" * 40)

    games = ["leagueoflegends", "counterstrike", "dota2"]
    tournaments = ["LEC Spring", "IEM Katowice", "The International"]

    for game, tournament in zip(games, tournaments):
        print(f"\n🎮 Testing {game.upper()} - {tournament}")
        print("-" * 30)

        try:
            async with LiquipediaAPI(game) as api:
                # Test tournament info
                print("📋 Tournament Info:")
                tournament_info = await api.get_tournament_info(tournament)
                for key, value in tournament_info.items():
                    print(f"   {key}: {value}")

                # Test upcoming matches
                print("\n⚔️  Upcoming Matches:")
                matches = await api.get_upcoming_matches(tournament)
                print(f"   Found {len(matches)} matches")

                for i, match in enumerate(matches[:3], 1):  # Show first 3
                    print(f"   Match {i}:")
                    for key, value in match.items():
                        print(f"     {key}: {value}")

                print("\n" + "=" * 30)

        except Exception as e:
            print(f"❌ Error testing {game}: {e}")


async def test_api_error_handling():
    """Test API error handling."""
    print("\n🔧 Testing Error Handling")
    print("-" * 25)

    try:
        async with LiquipediaAPI("invalidgame") as api:
            result = await api.get_tournament_info("Invalid Tournament")
            print(f"Invalid game result: {result}")
    except Exception as e:
        print(f"Expected error for invalid game: {e}")


async def test_sensor_data_structure():
    """Test the data structure that sensors would receive."""
    print("\n📊 Testing Sensor Data Structure")
    print("-" * 35)

    async with LiquipediaAPI("leagueoflegends") as api:
        # Simulate coordinator data
        coordinator_data = {
            "tournament_info": await api.get_tournament_info("LEC Spring 2024"),
            "upcoming_matches": await api.get_upcoming_matches("LEC Spring 2024"),
        }

        print("🎯 Complete Coordinator Data:")
        print(f"   Data keys: {list(coordinator_data.keys())}")
        print(f"   Tournament info keys: {list(coordinator_data['tournament_info'].keys())}")
        print(f"   Matches count: {len(coordinator_data['upcoming_matches'])}")

        # Simulate Tournament Sensor
        print(f"\n🏆 Tournament Sensor Output:")
        tournament_name = coordinator_data['tournament_info'].get('name', 'Unknown')
        print(f"   native_value: {tournament_name}")
        print(f"   extra_state_attributes:")

        tournament_attrs = {
            "status": coordinator_data['tournament_info'].get("status"),
            "prize_pool": coordinator_data['tournament_info'].get("prize_pool"),
            "start_date": coordinator_data['tournament_info'].get("start_date"),
            "end_date": coordinator_data['tournament_info'].get("end_date"),
            "last_updated": "2024-01-24T10:30:00Z",
        }

        for key, value in tournament_attrs.items():
            print(f"     {key}: {value}")

        # Simulate Matches Sensor
        print(f"\n⚔️  Matches Sensor Output:")
        matches = coordinator_data['upcoming_matches']
        print(f"   native_value: {len(matches)}")
        print(f"   extra_state_attributes:")
        print(f"     matches: {matches}")
        print(f"     last_updated: 2024-01-24T10:30:00Z")


if __name__ == "__main__":
    print("🧪 Simple Liquipedia API Testing")
    print("(No Home Assistant dependencies required)")
    print("=" * 50)

    asyncio.run(test_api_simple())
    asyncio.run(test_api_error_handling())
    asyncio.run(test_sensor_data_structure())

    print("\n✨ Test Complete!")
    print("\n💡 Key Insights:")
    print("   - The API returns placeholder data (modify api.py for real data)")
    print("   - Tournament sensor shows tournament name as native_value")
    print("   - Matches sensor shows match count as native_value")
    print("   - Both sensors include detailed attributes")
    print("\n🔧 Next Steps:")
    print("   - Install aiohttp: pip install aiohttp")
    print("   - Modify api.py to fetch real Liquipedia data")
    print("   - Test in Home Assistant environment")
