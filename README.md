# HACS Liquipedia Integration

A Home Assistant custom integration that tracks an esports team or a tournament
on Liquipedia.

## Features

- Find a team's matches automatically across League of Legends, Counter-Strike, Rocket League, and Valorant
- Follow an ongoing tournament or one starting in the next 30 days, with an optional team filter
- Keep manual Match Schedule page entry available for unlisted tournaments
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

Go to **Settings → Devices & services → Add integration**, search for
**Liquipedia Integration**, and choose a tracking mode.

- **Follow a team.** Enter the team name and select one or more supported games.
  Confirm which Liquipedia team page to follow in each game. Open the entry's
  configuration to change the games or pages later.
- **Follow a tournament.** Choose a game and select an ongoing or upcoming
  tournament, or enter its schedule page manually. The team filter is optional.
  Enter the team's Liquipedia page title as it appears in the results (for
  example, `Team Liquid`). You can change or clear the filter in the entry's
  configuration. Existing tournament entries keep their entities on upgrade.

## Usage

Once configured, the integration provides a timestamp sensor whose state is the
scheduled start time of the next match. It also provides a match-running binary
sensor. That entity switches on when the source explicitly marks a tracked
match as live. Match details are exposed as attributes including `title`,
`team1`, `team2`, `tournament`, and `best_of`.

Team tracking uses each selected team's upcoming and ongoing match list. The
next match is the earliest one reported across the selected games. It includes
the game and opponent in its attributes. Liquipedia caches team pages, so their
matches and live indicators can lag behind the main ticker. When a game fails
to refresh, the `unavailable_games` attribute lists it. A confirmed live match still shows
as on. If the remaining games report no live match, the live sensor state is
unknown while the data is incomplete.

The list comes from the selected wiki’s tournament ticker, using a rolling
30-day window. Finished tournaments are excluded. Selecting a tournament uses
its embedded match table or an existing Match Schedule link; tournaments without
a supported schedule require manual entry. Availability depends on Liquipedia’s
data and ticker support for the game.

For manual entry, enter the title of the tournament's Match Schedule page, exactly as it appears
after the game name in its Liquipedia URL. For example, this URL:
`https://liquipedia.net/leagueoflegends/First_Stand_Tournament/2026/Match_Schedule`
uses the page title `First Stand Tournament/2026/Match Schedule`. Choose a page
that has a Match Schedule table and contains future matches.

The integration refreshes data every five minutes using Liquipedia's MediaWiki
API. With no future match in the source, the timestamp sensor has no value.

## Supported Games for Tournament Tracking

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

Every pull request targeting `main` runs pytest, hassfest, and HACS validation.
Apply exactly one version label before merging it:

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

Match data comes from [Liquipedia](https://liquipedia.net/) and is available
under [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/). The
integration is independent of Liquipedia and Team Liquid.
