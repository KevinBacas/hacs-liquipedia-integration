"""Interactive sensor testing script with real-time monitoring."""
import asyncio
import sys
import os
import time
from datetime import datetime

# Add the parent directory to the path so we can import the custom component
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from custom_components.liquipedia.sensor import LiquipediaDataUpdateCoordinator
from custom_components.liquipedia.const import CONF_GAME, CONF_TOURNAMENT


class MockHomeAssistant:
    """Mock Home Assistant instance."""
    pass


class MockConfigEntry:
    """Mock config entry."""
    def __init__(self, entry_id="interactive_test", game="leagueoflegends", tournament=""):
        self.entry_id = entry_id
        self.data = {
            CONF_GAME: game,
            CONF_TOURNAMENT: tournament,
        }


async def monitor_sensor_updates(game, tournament, duration_seconds=60):
    """Monitor sensor updates in real-time."""
    print(f"\n📡 Starting real-time monitoring for {game} - {tournament}")
    print(f"⏱️  Duration: {duration_seconds} seconds")
    print("=" * 60)

    hass = MockHomeAssistant()
    config_entry = MockConfigEntry(game=game, tournament=tournament)
    coordinator = LiquipediaDataUpdateCoordinator(hass, config_entry)

    start_time = time.time()
    update_count = 0

    while time.time() - start_time < duration_seconds:
        try:
            print(f"\n🔄 Update #{update_count + 1} at {datetime.now().strftime('%H:%M:%S')}")

            # Fetch fresh data
            data = await coordinator._async_update_data()

            if data:
                tournament_info = data.get("tournament_info", {})
                upcoming_matches = data.get("upcoming_matches", [])

                print(f"🏆 Tournament: {tournament_info.get('name', 'Unknown')}")
                print(f"📊 Status: {tournament_info.get('status', 'Unknown')}")
                print(f"💰 Prize Pool: {tournament_info.get('prize_pool', 'Unknown')}")
                print(f"⚔️  Upcoming Matches: {len(upcoming_matches)}")

                if upcoming_matches:
                    print("   Next matches:")
                    for i, match in enumerate(upcoming_matches[:3], 1):  # Show first 3
                        print(f"     {i}. {match.get('team1', 'TBD')} vs {match.get('team2', 'TBD')} "
                              f"({match.get('format', 'TBD')})")

            update_count += 1

            # Wait 10 seconds before next update
            await asyncio.sleep(10)

        except KeyboardInterrupt:
            print("\n⏹️  Monitoring stopped by user")
            break
        except Exception as e:
            print(f"❌ Error during update: {e}")
            await asyncio.sleep(5)

    print(f"\n📈 Monitoring complete! Total updates: {update_count}")


async def interactive_test():
    """Run interactive testing session."""
    print("🎮 Interactive Liquipedia Sensor Testing")
    print("=" * 50)

    # Get user input
    print("\nAvailable games:")
    games = ["leagueoflegends", "counterstrike", "dota2", "valorant", "overwatch"]
    for i, game in enumerate(games, 1):
        print(f"  {i}. {game}")

    try:
        choice = input("\nSelect game (1-5) or enter custom: ").strip()

        if choice.isdigit() and 1 <= int(choice) <= len(games):
            game = games[int(choice) - 1]
        else:
            game = choice if choice else "leagueoflegends"

        tournament = input("Enter tournament name (or leave empty): ").strip()

        print(f"\n🎯 Testing configuration:")
        print(f"   Game: {game}")
        print(f"   Tournament: {tournament or 'General'}")

        # Single test
        print(f"\n🧪 Running single test...")
        hass = MockHomeAssistant()
        config_entry = MockConfigEntry(game=game, tournament=tournament)
        coordinator = LiquipediaDataUpdateCoordinator(hass, config_entry)

        data = await coordinator._async_update_data()

        print("✅ Raw API Data:")
        print(f"   {data}")

        # Ask if user wants monitoring
        monitor = input("\n🔄 Start real-time monitoring? (y/N): ").strip().lower()
        if monitor in ['y', 'yes']:
            duration = input("Duration in seconds (default 60): ").strip()
            duration = int(duration) if duration.isdigit() else 60
            await monitor_sensor_updates(game, tournament, duration)

    except KeyboardInterrupt:
        print("\n👋 Test session ended by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")


async def quick_test_all_games():
    """Quick test of all supported games."""
    print("\n🚀 Quick Test - All Games")
    print("=" * 30)

    games = ["leagueoflegends", "counterstrike", "dota2", "valorant", "overwatch"]

    for game in games:
        print(f"\n🎮 Testing {game.upper()}...")
        try:
            hass = MockHomeAssistant()
            config_entry = MockConfigEntry(game=game, tournament="")
            coordinator = LiquipediaDataUpdateCoordinator(hass, config_entry)

            data = await coordinator._async_update_data()
            tournament_info = data.get("tournament_info", {})
            matches = data.get("upcoming_matches", [])

            print(f"   ✅ Tournament: {tournament_info.get('name', 'None')}")
            print(f"   ✅ Matches: {len(matches)} found")

        except Exception as e:
            print(f"   ❌ Error: {e}")


if __name__ == "__main__":
    print("🧪 Liquipedia Interactive Testing Suite")
    print("Choose testing mode:")
    print("1. Interactive test (recommended)")
    print("2. Quick test all games")
    print("3. Monitor specific game (default: League of Legends)")

    try:
        mode = input("\nSelect mode (1-3): ").strip()

        if mode == "2":
            asyncio.run(quick_test_all_games())
        elif mode == "3":
            asyncio.run(monitor_sensor_updates("leagueoflegends", "LEC", 30))
        else:
            asyncio.run(interactive_test())

    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
