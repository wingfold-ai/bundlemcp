# Proposal: complete release engineering

## Why

bundlemcp publishes `:latest` and `:<sha>` images from `main`, but it has never cut a release: there are no semver tags,
no changelog and no release notes, so a consumer of the metering hook cannot tell from a release when the hook protocol
changed. The backup runbook documents a restore rehearsal that nothing schedules, CI never runs the frontend typecheck
(only the build), and the runtime-version rules are not enforced where they could be — `apps/web/package.json` declares
no `engines`, and the docs and diagrams jobs run Node 22.

## What Changes

- **Restore rehearsal (DEP-8):** a workflow rehearses the documented restore against the compose stack once per release
  cycle (on every release tag, and on demand), so the runbook is exercised, not only written down.
- **CI gates (DEP-10):** the frontend job also runs `npm run typecheck`.
- **Releases (DEP-11):** pushing a `v<semver>` tag publishes both images under that version, and a GitHub release whose
  notes come from a maintained `CHANGELOG.md`; every release note states the metering-hook protocol version and calls
  out a change to it.
- **Runtime versions (ARC-2):** `apps/web/package.json` declares `engines.node >= 24`, and every CI and publishing job
  that runs Node uses 24 or later. The Python half of ARC-2 moved to its own change,
  [adopt-python-3-14](../../changes/archive/2026-10-15-adopt-python-3-14/proposal.md), which settled it as 3.14; the
  ARC-2 delta here carries that text unchanged so archiving this change does not undo it.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `deployment`: DEP-8 (restore rehearsed once per release cycle), DEP-10 (frontend typecheck in CI), DEP-11 (tagged
  semver releases with changelog and release notes naming the metering-hook protocol version).
- `architecture`: ARC-2 (Node ≥ 24 enforced by `engines` and used by every job).

## Impact

- **CI:** `.github/workflows/ci.yml` (typecheck step, Node 24 in the docs and diagrams jobs),
  `.github/workflows/publish-docs.yml` (Node 24), `.github/workflows/publish.yml` (tag trigger and semver image tags), a
  new release workflow and a restore-rehearsal workflow.
- **Repository:** a new `CHANGELOG.md`; `apps/web/package.json` (`engines`).
- **Docs:** `docs/self-hosting/deploy.md` (*Backups* — where the rehearsal runs; image tags for pinning a release),
  `docs/integrate/metering-hook.md` (where the protocol version is announced), `CONTRIBUTING.md` (how a release is cut).
- **Depends on** nothing. No ADR: these are operational rules, not architectural decisions.
