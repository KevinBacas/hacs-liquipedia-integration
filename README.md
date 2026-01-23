# HACS Liquipedia Integration

A Home Assistant custom integration that provides access to Liquipedia data for esports tournaments, teams, and players.

## Features

- Access to tournament data from Liquipedia
- Player and team information
- Match results and schedules
- Support for multiple esports games

## Installation

### Via HACS (Recommended)

1. Ensure you have [HACS](https://hacs.xyz/) installed
2. Go to HACS → Integrations
3. Click the three dots in the top right corner and select "Custom repositories"
4. Add this repository URL and select "Integration" as the category
5. Click "Add"
6. Search for "Liquipedia Integration" and install it
7. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/liquipedia` folder to your Home Assistant's `custom_components` directory
2. Restart Home Assistant
3. Go to Configuration → Integrations
4. Click the "+" button and search for "Liquipedia"

## Configuration

1. Go to Configuration → Integrations
2. Click the "+" button
3. Search for "Liquipedia Integration"
4. Follow the setup wizard

## Usage

Once configured, the integration will provide sensors with:
- Tournament information
- Player statistics
- Team rankings
- Match schedules

## Supported Games

- League of Legends
- Counter-Strike
- Dota 2
- Valorant
- And more...

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This integration is not officially affiliated with Liquipedia or Team Liquid. It uses publicly available data from Liquipedia's APIs and pages.