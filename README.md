# HACS Liquipedia Integration

A Home Assistant custom integration that exposes the next upcoming esports match
from Liquipedia.

## Features

- Select a game and a Liquipedia Match Schedule page during setup
- Create one timestamp sensor for the next scheduled match
- Create a match-running binary sensor when Liquipedia explicitly marks a match live
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
sensor. That entity is on only when Liquipedia explicitly identifies a match as
live; it is off when no live match is reported. Match details are exposed as
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

### CI and releases

Every pull request targeting `main` runs hassfest and HACS validation. Apply
exactly one version label before merging it:

| Label | Use when the change is… |
|-------|--------------------------|
| `bump:patch` | a backwards-compatible bug fix |
| `bump:minor` | backwards-compatible new functionality |
| `bump:major` | a breaking change |

When validation succeeds, the pull request gets a GitHub release candidate
tagged as `v{new-version}-rc.{pr-number}`. Once it is merged, the stable
release workflow validates `main`, updates `manifest.json`, creates the stable
tag, and publishes the GitHub release.

This follows [Semantic Versioning](https://semver.org/). Use Conventional
Commits (`fix:`, `feat:`, and `feat!:` or a `BREAKING CHANGE:` footer) in the
pull request commits to make the correct label easy for reviewers to choose.
The label remains the explicit release decision used by automation.

The repository settings must allow `github-actions[bot]` to push its release
commit to `main`; if branch protection is enabled, permit this app to bypass
the rule.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This integration is not officially affiliated with Liquipedia or Team Liquid. It uses publicly available data from Liquipedia's APIs and pages.
