# Maintaining the Liquipedia integration

The [README](../README.md) describes installation, supported games, and entity
behavior. Python 3.13 and the minimum Home Assistant release declared in
[`hacs.json`](../hacs.json) are the local validation baseline. The test
requirements pin that Core release.

## Code map

| Path | Responsibility |
| --- | --- |
| `custom_components/liquipedia/config_flow.py` | Team and tournament setup, MediaWiki title validation, duplicate detection, and entry options |
| `custom_components/liquipedia/__init__.py` | First refresh, entry-owned coordinator, platform setup and unload |
| `custom_components/liquipedia/coordinator.py` | Fetch team pages or a tournament on a shared five-minute interval, merge results and report coverage |
| `custom_components/liquipedia/api.py` | Shared HTTP session, MediaWiki calls, request pacing, caching, tournament discovery and schedule parsing |
| `custom_components/liquipedia/team_parser.py` | Parse the upcoming and ongoing match cards for a canonical team page |
| `custom_components/liquipedia/sensor.py` and `binary_sensor.py` | Timestamp and explicit live state from the same coordinator snapshot |
| `custom_components/liquipedia/strings.json` and `translations/` | Setup, options, entity, and error strings. Keep English and French keys in sync. |
| `tests/` | Offline tests for the API, parsers, configuration, coordinator and entry lifecycle |

## Compatibility and source behavior

- Entries created before team mode have no `mode` and still represent tournaments.
  Persisted configuration and registry IDs are compatibility contracts. The two
  entity unique IDs use the config entry ID with `_upcoming_match` and
  `_match_running` suffixes. Verify older entries and options reloads when changing
  setup or entity registration.
- Home Assistant shares one refresh across both entities. A successful empty
  feed yields no upcoming match. A failed refresh of every source makes the
  entities unavailable. With partial team data, the snapshot includes the failed
  games. A positive live marker still turns the binary sensor on. Its state is
  unknown if the readable games have no confirmed live match.
- Treat an explicit match status as evidence for live state. A scheduled time
  and a stream link provide no such evidence. Exclude explicitly live and
  finished matches from the next scheduled match.
- Use only Liquipedia's public MediaWiki `api.php` endpoints for automated
  access. Share pacing across wiki paths on the same host. Allow at least two
  seconds between requests and 30 seconds between `action=parse` requests, reuse
  the HTTP session, request gzip support, and preserve the identifying user agent
  and attribution. Honor `Retry-After` host-wide on rate-limit and service-unavailable
  responses. [Liquipedia API terms](https://liquipedia.net/api-terms-of-use)
- Tournament discovery uses the wiki's ticker with a 30-day upcoming window.
  Tournament schedules use an embedded match table or a linked Match Schedule
  page. Team tracking uses each wiki's team page widget, with game-specific
  format differences and delays from Liquipedia's cache.
- Before enabling a new game or accepting a new markup variant, verify the
  actual MediaWiki response. Keep a minimal representative offline fixture with
  its wiki, page title and observed format. Cover empty schedules, missing or
  changed markup, redirects, status markers and partial failures where relevant.
  Coordinate manual upstream requests so concurrent agents share the rate budget.

## Local validation

From the repository root, using Python 3.13:

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-test.txt
python -m ruff check custom_components tests
python -m pytest -q
git diff --check
```

Use the narrowest relevant test file while making changes, then run the complete
suite. CI also runs hassfest and HACS validation. For workflow changes, validate
the YAML and shell steps locally where possible. If a test Home Assistant
instance is available and authorized, confirm configuration for the affected
mode, an options reload and the entity states through the Home Assistant UI.
Record which checks actually ran.

## Pull requests and releases

- Every PR targeting `main` runs Ruff, pytest, hassfest and HACS validation.
  Exactly one of `bump:patch`, `bump:minor`, or `bump:major` selects the release
  increment. Check the PR labels before pushing to an active preview branch.
- A labeled PR from this repository publishes an RC only if its validation
  succeeds. The tag is `v<version>-rc.<workflow-run-number>` and points to the
  validated merge result plus the version change. A rerun can reuse its tag.
- After a labeled PR merges, the stable workflow validates and tags that merge
  plus the version change. Later commits on `main` stay outside the tag. The workflow
  synchronizes the manifest on `main` in the same atomic push as the tag.
  If a concurrent push advances `main`, retry the publishing job to fetch the
  current branch. If publication fails after the push, retry the original run so
  it can reuse the tag. A stable tag already containing the requested merge blocks
  a stale release. If a labeled merge fails before tagging, recover its run before
  relying on the bump label of a later PR that includes that merge.
- When checking a published build, compare the version in `manifest.json` at the
  tag with the tag stripped of its leading `v`. Confirm the GitHub release
  points to that tag and has the expected prerelease flag.
- The stable workflow receives merged-PR events on the base repository.
  Keep validation on trusted commits from `main` and branch or tag writes
  restricted to the publishing job.

## Skills for future sessions

Use these Codex skills when available. The pinned sources let another maintainer
review and reinstall the same versions through the Codex skill installer.

| Skill | Use | Source |
| --- | --- | --- |
| `ha-integration-knowledge` | Entry and entity lifecycle, config flows, domain conventions | [Home Assistant Core, f95570b](https://github.com/home-assistant/core/tree/f95570bef907bc0de8e566932cca56b64611dcce/.claude/skills/ha-integration-knowledge) |
| `python-testing-patterns` | Focused pytest regressions, async mocks, fixtures and error cases | [wshobson/agents, 91ff753](https://github.com/wshobson/agents/tree/91ff75307f5668916f3eb77d5ba556266c961376/plugins/python-development/skills/python-testing-patterns) |

When changing the skill selection, keep this table and `AGENTS.md` in sync.
The repository guide and CI commands are usable without the external skills.
