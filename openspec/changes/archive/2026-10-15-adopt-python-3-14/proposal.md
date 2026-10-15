# Proposal

## Why

ARC-2 pins the images to `python:3.13`, but the project rule is to adopt the latest stable versions, and Python 3.14 is
the latest stable release. Dependabot has proposed the move twice (#111 for `examples/echo-mcp`, #114 for the gateway),
and #114 shows why a piecemeal bump is unsafe: it moves only the gateway's runtime stage to 3.14 while the builder stage
still builds the virtualenv on 3.13, so the image builds but fails the integration suite. The open change
`complete-release-engineering` already proposes 3.14 but leaves it as an undecided question; this change settles it as
3.14 and ships it on its own, ahead of the release-engineering work.

## What Changes

- The gateway is built, tested and shipped on Python 3.14: both stages of `apps/gateway/Dockerfile`, the example
  upstream images (`examples/echo-mcp`, `examples/oauth-demo-mcp`) and every CI job that sets up Python.
- One file, a new `.python-version` at the repository root, declares the shipped version. A hermetic test checks that
  every Dockerfile base image and every CI `python-version` names that version, so a partial bump like #114 fails in
  the backend job instead of in integration.
- Dependabot's Docker updates are grouped so the Python base images move in one pull request, and
  `examples/oauth-demo-mcp` is added to the directories it watches.
- `requires-python = ">=3.13"` and ruff's `target-version = "py313"` stay: the library still supports 3.13, so code must
  not use 3.14-only syntax.
- `complete-release-engineering` drops its Python open decision and the Python parts of its tasks; its ARC-2 delta keeps
  the Python text this change introduces, so archiving it later does not undo this one.
- Supersedes Dependabot PRs #111 and #114.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `architecture`: ARC-2 moves from "images on `python:3.13`" to "built, tested and shipped on the latest stable Python
  (3.14)", with one declared version that images and CI must match.

## Impact

- **Images:** `apps/gateway/Dockerfile` (builder `ghcr.io/astral-sh/uv:python3.14-bookworm-slim`, runtime
  `python:3.14-slim-bookworm`), `examples/echo-mcp/Dockerfile`, `examples/oauth-demo-mcp/Dockerfile`.
- **CI:** the three `python-version: "3.13"` entries in `.github/workflows/ci.yml`; `.github/dependabot.yml`.
- **Development:** `.python-version` makes `uv sync` pick 3.14 locally, so existing `.venv`s are recreated on 3.14.
  Contributors on 3.13 can still install the workspace.
- **Docs:** the `FROM python:3.13-slim` example in `docs/connect/stdio-sidecar.md`. The pages that state the minimum
  (`docs/self-hosting/requirements.md`, `CONTRIBUTING.md`, `docs/arc42/02-constraints.md`) stay at "3.13 or newer".
- **Open changes:** `complete-release-engineering` (proposal, ARC-2 delta, tasks 1.1, 2.3 and 2.4).
- **ADR:** none. Following the latest stable release is an existing rule (ARC-2's original wording and the stack rule
  in `CLAUDE.md`), not a new architectural decision.
- No GitHub issue; the trigger is Dependabot PRs #111 and #114.
