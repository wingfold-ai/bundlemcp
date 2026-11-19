# Proposal

## Why

Dependabot's pull request description quotes the commits of the package it updates, and release commits often end in
`[skip ci]` (marked's `chore(release): 18.2.0 [skip ci]`, for instance). The squash merge takes its message from the
description, so the check rightly refuses such a description, but the pull request then waits for someone to edit it
by hand, as #224 did.

## What Changes

- In a Dependabot pull request, the release-entry workflow defuses every CI-skip marker in the description before
  checking it: `[skip ci]` and its bracketed variants become `(skip ci)`, and `skip-checks: true` loses its colon. It
  saves the description on the pull request, so the squash commit carries the defused text. Descriptions written by
  people are still refused as before.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `deployment`: modifies DEP-12 (every pull request carries its release): a CI-skip marker in a Dependabot
  description is defused instead of failing the check.

## Impact

- `tools/pull_request_release.py`: `defuse_skip_markers` and a `bot-description` command, with tests.
- `.github/workflows/release-entry.yml`: the description step defuses and saves a Dependabot description.
- `CONTRIBUTING.md`.
- No gateway behaviour changes. No ADR.
