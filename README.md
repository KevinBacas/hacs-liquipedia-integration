# HACS Liquipedia Integration

A Home Assistant custom integration that exposes the next upcoming esports match
from Liquipedia.

## Features

- Select a game and a Liquipedia Match Schedule page during setup
- Create one timestamp sensor for the next scheduled match
- Create a match-running binary sensor that is unavailable outside an active match
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

Once configured, the integration provides a timestamp sensor whose state is the
scheduled start time of the next match. It also provides a match-running binary
sensor. That entity is unavailable when no match is running and becomes
available/on when a scheduled match starts. Match details are exposed as
attributes including `title`, `team1`, `team2`, `tournament`, and `best_of`.

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

### CI & Release Candidates

Every pull request targeting `main` automatically runs two checks:

1. **Validate** – runs [hassfest](https://developers.home-assistant.io/docs/creating_integration_manifest/) and [HACS validation](https://github.com/hacs/action) to ensure the integration is well-formed.
2. **Release Candidate** – creates a GitHub pre-release once validation passes, *only* when a bump label is applied to the PR.

#### How to trigger a release candidate

Apply exactly one of these labels to your PR before (or after) pushing commits:

| Label | Effect | Example |
|-------|--------|---------|
| `bump:patch` | Increments the patch version | `0.2.0` → `0.2.1` |
| `bump:minor` | Increments the minor version | `0.2.0` → `0.3.0` |
| `bump:major` | Increments the major version | `0.2.0` → `1.0.0` |

The pre-release tag follows the format `v{new-version}-rc.{pr-number}` (e.g. `v0.3.0-rc.5`). The tag is re-created on every new commit, so the pre-release always reflects the latest state of the PR. If multiple bump labels are present the highest precedence wins (`major > minor > patch`).

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This integration is not officially affiliated with Liquipedia or Team Liquid. It uses publicly available data from Liquipedia's APIs and pages.
