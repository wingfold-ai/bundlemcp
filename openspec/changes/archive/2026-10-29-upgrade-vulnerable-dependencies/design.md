# Design

## Context

See [proposal.md](proposal.md). Python dependencies are resolved by uv into one workspace `uv.lock`; the gateway image
installs with `uv sync --frozen --no-dev`. `authlib` and `dnspython` are transitive: through `fastmcp`, and through
`pydantic[email]` → `email-validator` (pulled in by `fastmcp`). `apps/web` and
`docs/` each have an npm `package-lock.json`; CI installs both with `npm ci`.

## Goals / Non-Goals

**Goals:**

- `pip-audit` over `uv export --all-packages` and `npm audit` over both lockfiles report no known vulnerability.
- The declared floor of the direct dependency that carried the vulnerable transitive versions excludes them.

**Non-Goals:**

- A CI gate that keeps it that way (audit S4).
- Upper bounds on dependencies (audit N17); ARC-1 asks for `>=` floors only.

## Decisions

### Upgrade selectively with `--upgrade-package`, not a full `uv lock --upgrade`

`uv lock --upgrade-package fastmcp --upgrade-package authlib --upgrade-package dnspython`
moves only the affected packages. That keeps this change reviewable and makes a regression traceable to a vulnerable
package. A full refresh belongs in the routine Dependabot updates.

### Floor only the direct dependency

Only `fastmcp>=4.1.2` is raised in `pyproject.toml`. Declaring `authlib` or `dnspython` directly would add
dependencies the code does not import. The lock pins them, and the S4 gate will catch a regression.

### npm: targeted bumps, then `npm audit fix`, no `--force`

`nuxt` to the latest 4.6 patch and `@nuxt/ui` to 4.12, followed by `npm audit fix`. `--force` is ruled out because it
may jump majors. If a fix needs a major (none does per the 2026-10-29 audit), the task stops and asks.

## Risks / Trade-offs

- [fastmcp 4.1 changes client behaviour the pool relies on] → mitigated by the pooled-session tests, the conformance
  harness per protocol revision and the compose integration suite. The fastmcp 4.1 changelog is read before the bump,
  and any deprecation it introduces is noted in the PR.
- [A Nuxt patch changes generated types] → `npm run openapi`, `npm run typecheck` and the build run in the gates.
