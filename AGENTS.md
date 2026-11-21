# Working on the Liquipedia integration

Read [the maintainer guide](docs/maintainers.md) before changing the integration
or its CI. Update the guide in the same change whenever the architecture, source
contract, supported games, validation commands, or release process changes.
Keep user-facing setup and behavior in [README.md](README.md). Use
`ha-integration-knowledge` for the Home Assistant contract and
`python-testing-patterns` when reviewing or writing regression tests.

Use the following multi-agent workflow for each implementation change. The lead agent owns the scope, integrates the work, and reports verification and release status. For small changes, combine implementation and validation in one assignment and keep the final review independent.

| Role | Preferred model | Responsibility |
|---|---|---|
| Technical design | `gpt-6.2-astra`, high reasoning | Verify the Liquipedia source and Home Assistant contracts. Agree on the data shape, compatibility and failure behavior before work that depends on them. |
| Liquipedia implementation | `gpt-6.2-sol`, high reasoning | Own API, parsing, throttling and cache changes, with focused data tests. |
| Home Assistant implementation | `gpt-6.2-sol`, high reasoning | Own configuration flows, options, translations and entities, with focused regression tests. |
| Validation and CI | `gpt-6.2-sol`, medium reasoning | Run tests, cover affected user flows, and verify packaging or release checks when relevant. |
| Independent review | `gpt-6.2-astra`, high reasoning | Review the assembled diff for compatibility, incorrect live states, request volume and gaps in verification. Report findings to the lead. |

Use the closest available model for each role if a preferred model is unavailable. Give parallel agents disjoint file ownership and a shared contract. Keep investigation read-only when the user asks for a plan or an assessment. The lead coordinates real Liquipedia requests across agents so the shared per-host rate limits are respected.

Preserve existing configuration entries and entity IDs. Distinguish an empty calendar from a failed source, and require explicit upstream evidence before showing a match as live. Use offline fixtures in CI and validate a new game's data against the public MediaWiki API before enabling it.

Run the local validation commands in the maintainer guide before handing off a
change. Check the pull request labels before pushing, since a bump label on a
branch in this repository can publish a preview. When publication is in scope,
verify that the published tag matches the integration manifest.
