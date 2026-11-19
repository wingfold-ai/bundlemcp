# Proposal

## Why

Dependabot titles a group holding a single update after the package, and appends the directory and the group:
`chore: Bump likec4 from 1.59.4 to 1.60.0 in /docs in the npm group across 1 directory` is 85 characters. The title
check allows 72, so such a pull request fails CI for nothing it changed and waits for someone to retitle it by hand.
Separately, the E2E test of the audit CSV export (E2E-28) fails now and then: it reads the number of successful
calls right after making two, but the gateway writes audit records after answering, so the count can still grow.

## What Changes

- **Dependabot titles:** when a Dependabot pull request's title is longer than 72 characters, the release-entry
  workflow shortens it before checking it: first it drops the group and directory count Dependabot appends, then the
  version updated from, then the directory. It saves the shortened title on the pull request, so the squash commit
  carries it. Titles written by people are still checked as they are.
- **E2E-28:** the test waits until the count of successful calls stops changing before it compares the page and the
  CSV against it.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `deployment`: modifies DEP-12 (every pull request carries its release): a long Dependabot title is shortened
  instead of failing the check.

## Impact

- `tools/pull_request_release.py`: `shorten_bot_title` and a `bot-title` command, with tests.
- `.github/workflows/release-entry.yml`: the labels job shortens a Dependabot title, and the entry job uses it.
- `apps/web/tests/audit.spec.ts`: E2E-28 waits for the audit count to settle.
- `CONTRIBUTING.md` and the comment in `.github/dependabot.yml`.
- No gateway behaviour changes. No ADR.
