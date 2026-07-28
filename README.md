# HACS Liquipedia Integration

A Home Assistant custom integration that exposes the next upcoming esports match
from Liquipedia.

## Features

- Select a game and a Liquipedia Match Schedule page during setup
- Create one timestamp sensor for the next scheduled match
- Expose the match title, both team names, tournament, and format as attributes

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

Once configured, the integration provides a timestamp sensor. Its state is the
scheduled start time of the next match. Attributes include `title`, `team1`,
`team2`, `tournament`, and `best_of`.

Enter the title of the tournament's Match Schedule page, exactly as it appears
after the game name in its Liquipedia URL. For example, this URL:
`https://liquipedia.net/leagueoflegends/First_Stand_Tournament/2026/Match_Schedule`
uses the page title `First Stand Tournament/2026/Match Schedule`. Choose a page
that has a Match Schedule table and contains future matches.

The integration uses Liquipedia's supported MediaWiki API and polls no more
than once every five minutes. If no future match is available, the sensor has
no state until one appears.

## Supported Games

- League of Legends
- Counter-Strike
- Dota 2
- Valorant
- Overwatch
- Hearthstone
- StarCraft
- StarCraft II

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This integration is not officially affiliated with Liquipedia or Team Liquid. It uses publicly available data from Liquipedia's APIs and pages.
