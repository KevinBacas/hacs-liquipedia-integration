#!/usr/bin/env python3
"""Test runner for Liquipedia integration."""
import subprocess
import sys
import os


def run_command(command, description):
    """Run a command and handle the output."""
    print(f"\n🔄 {description}")
    print("=" * 50)

    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=os.path.dirname(__file__))

        if result.returncode == 0:
            print("✅ Success!")
            if result.stdout:
                print(result.stdout)
        else:
            print("❌ Failed!")
            if result.stderr:
                print(f"Error: {result.stderr}")
            if result.stdout:
                print(f"Output: {result.stdout}")

        return result.returncode == 0
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False


def main():
    """Run all tests."""
    print("🧪 Liquipedia Integration Test Suite")
    print("=" * 50)

    # Check if we're in the right directory
    if not os.path.exists("../custom_components/liquipedia"):
        print("❌ Error: Please run this script from the tests/ directory")
        sys.exit(1)

    # Test options
    print("\nSelect test type:")
    print("1. Unit tests (pytest)")
    print("2. Sensor output test (shows actual data)")
    print("3. Interactive test (real-time monitoring)")
    print("4. All tests")

    choice = input("\nEnter choice (1-4): ").strip()

    if choice == "1" or choice == "4":
        # Install test requirements if needed
        print("\n📦 Installing test requirements...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                      capture_output=True)

        # Run pytest
        success = run_command("python -m pytest -v", "Running Unit Tests")
        if not success and choice == "4":
            print("Unit tests failed, continuing with other tests...")

    if choice == "2" or choice == "4":
        # Run sensor output test
        run_command("python test_sensor_output.py", "Running Sensor Output Test")

    if choice == "3":
        # Run interactive test
        print("\n🎮 Starting Interactive Test...")
        subprocess.run([sys.executable, "interactive_test.py"])

    if choice == "4":
        print("\n✨ All tests completed!")
        print("\n💡 Tips for debugging:")
        print("   - Check test_sensor_output.py for detailed sensor data")
        print("   - Use interactive_test.py for real-time monitoring")
        print("   - Modify the API in api.py to connect to real Liquipedia")
        print("   - Check Home Assistant logs for integration issues")


if __name__ == "__main__":
    main()
