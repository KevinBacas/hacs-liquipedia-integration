# Testing Documentation for Liquipedia Integration

This directory contains comprehensive tests for the Liquipedia Home Assistant integration, allowing you to see what data is being returned by your sensors.

## 🧪 Test Files Overview

### Core Test Files
- **`standalone_sensor_test.py`** - ⭐ **Start here!** Complete sensor testing without dependencies
- **`test_api.py`** - Unit tests for the API layer
- **`test_sensor.py`** - Unit tests for the sensor components
- **`conftest.py`** - Test configuration and fixtures

### Helper Scripts
- **`simple_api_test.py`** - Basic API testing (requires aiohttp)
- **`test_sensor_output.py`** - Full sensor testing (requires Home Assistant)
- **`interactive_test.py`** - Real-time monitoring script
- **`run_tests.py`** - Test runner script

## 🚀 Quick Start - See Your Sensor Data

Run this command to immediately see what your sensors are returning:

```bash
cd /path/to/your/integration
python3 tests/standalone_sensor_test.py
```

This will show you:
- ✅ **Raw API data** being fetched
- ✅ **Tournament sensor output** (name, status, prize pool, etc.)
- ✅ **Matches sensor output** (count, upcoming matches, etc.)
- ✅ **Error handling** scenarios

## 📊 What You'll See

### Tournament Sensor Output
```
🏆 Tournament Sensor Output:
   Name: Leagueoflegends Tournament Info
   Unique ID: test_leagueoflegends_tournament
   Native Value: LEC Spring 2024
   Attributes:
     status: Active
     prize_pool: €200,000
     start_date: 2024-01-22
     end_date: 2024-03-15
     location: Online
     organizer: Riot Games
```

### Matches Sensor Output
```
⚔️  Matches Sensor Output:
   Name: Leagueoflegends Upcoming Matches
   Unique ID: test_leagueoflegends_matches
   Native Value: 2
   Attributes:
     total_matches: 2
     next_match: G2 Esports vs Fnatic at 2024-01-25T18:00:00Z
```

## 🔧 Advanced Testing

### 1. Unit Tests (requires setup)
```bash
# Create virtual environment
python3 -m venv test_env
source test_env/bin/activate

# Install dependencies
pip install -r tests/requirements.txt

# Run unit tests
python -m pytest tests/ -v
```

### 2. Interactive Testing
```bash
python3 tests/interactive_test.py
```

### 3. API-Only Testing
```bash
python3 tests/simple_api_test.py
```

## 🎯 Understanding Your Sensors

### Tournament Sensor
- **Native Value**: Tournament name (what shows in HA)
- **Attributes**: Rich data including status, prize pool, dates, organizer
- **Use Case**: Display tournament info, trigger automations based on status

### Matches Sensor
- **Native Value**: Number of upcoming matches
- **Attributes**: Complete match details, next match info
- **Use Case**: Count matches, show next game, stream links

## 🛠️ Debugging Your Integration

### Common Issues and Solutions

1. **"No matches found"**
   - Check [api.py](../custom_components/liquipedia/api.py) implementation
   - Verify tournament name spelling
   - Test with `standalone_sensor_test.py`

2. **"Tournament not found"**
   - Validate API endpoint in [const.py](../custom_components/liquipedia/const.py)
   - Check game name in supported games list
   - Test API connectivity

3. **"Sensor shows Unknown"**
   - API is returning empty data
   - Check network connectivity
   - Verify API response format

### Modifying Test Data

Edit `standalone_sensor_test.py` to test with your data:
```python
# In MockLiquipediaAPI.get_tournament_info()
return {
    "name": "Your Tournament",
    "status": "Your Status", 
    "prize_pool": "Your Prize Pool",
    # ... add your data structure
}
```

## 📝 Test Results Explained

### Raw Coordinator Data
This is exactly what your sensors receive from the API. It should match the structure expected by your sensor classes.

### Sensor Native Values
- **Tournament**: Shows the main tournament name
- **Matches**: Shows the count of upcoming matches

### Sensor Attributes
All the detailed information available in Home Assistant's developer tools under each sensor.

## 🎮 Testing Different Games

The tests automatically check multiple games:
- League of Legends (`leagueoflegends`)
- Counter-Strike (`counterstrike`) 
- Dota 2 (`dota2`)
- Valorant (`valorant`)
- Overwatch (`overwatch`)

Each game can have different data structures - use the tests to verify your implementation works across all supported games.

## 🔗 Home Assistant Integration

When working with Home Assistant:

1. **Install** your integration in HA
2. **Configure** using the config flow
3. **Check** sensor values in Developer Tools > States
4. **Compare** with test output to verify correctness

### Example Home Assistant Automation
```yaml
automation:
  - alias: "Notify when LEC match starts"
    trigger:
      - platform: template
        value_template: "{{ state_attr('sensor.leagueoflegends_upcoming_matches', 'next_match')['time'] | as_timestamp | int < now().timestamp() + 300 }}"
    action:
      - service: notify.mobile_app
        data:
          message: "{{ state_attr('sensor.leagueoflegends_upcoming_matches', 'next_match')['team1'] }} vs {{ state_attr('sensor.leagueoflegends_upcoming_matches', 'next_match')['team2'] }} starting soon!"
```

## 💡 Tips

1. **Start with standalone tests** - No dependencies required
2. **Use real API data** - Modify [api.py](../custom_components/liquipedia/api.py) to fetch actual Liquipedia data
3. **Test error scenarios** - Network failures, API changes, etc.
4. **Monitor in real-time** - Use interactive test for live debugging

## 🆘 Getting Help

If sensors aren't returning expected data:
1. Run `standalone_sensor_test.py` to see current output
2. Compare with expected Home Assistant behavior
3. Check Home Assistant logs for errors
4. Verify API implementation in your component files
