# Proposal

## Why

Python 3.15 is the latest stable release. ARC-2 says the gateway is built, tested and shipped on the latest stable
Python and that one declared version governs every image and CI job. Dependabot's #156 moved only three runtime images
to 3.15. Building on 3.14 and running on 3.15 failed integration and conformance, and the ARC-2 test flagged the
mismatch. Adopting 3.15 means moving the declared version, CI, every image and the locked dependencies together.

## What Changes

- **The declared version becomes 3.15** (ARC-2, modified). This covers:
  - `.python-version`;
  - every `python-version` in `.github/workflows/`;
  - every Python image: the gateway's build and runtime stages, and the three example upstreams, including
    `conformance-mcp`, which #156 missed.
- **The gateway builds on the runtime's own base.** `astral-sh/uv` publishes no Debian bookworm image for 3.15, so the
  build stage starts from `python:3.15-slim-bookworm`, the same base as the runtime, and copies in the pinned uv it
  already copies.
- **Dependencies that need a newer release for 3.15** are relocked:
  - `greenlet` 3.5.3 → 3.5.6. The older one breaks SQLAlchemy's async layer on 3.15 ("greenlet context must be a
    contextvars.Context").
  - `cffi` 2.0.0 → 2.1.1, `markupsafe` 3.0.3 → 3.0.4, `pydantic-core` → 2.50.1 and `websockets` 16 → 17.3, for their
    3.15 wheels.
  - `sqlalchemy` 2.0.51 → 2.1.6, for its 3.15 wheels.
- `requires-python` stays `>=3.13`. Running outside a container on 3.13 or 3.14 still works.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `architecture`: ARC-2 (the shipped version named in the text and its scenario becomes 3.15).

## Impact

- **Resolves:** Dependabot #156, which this change completes on its branch.
- **Files:**
  - `.python-version`
  - `.github/workflows/ci.yml` and `restore-rehearsal.yml`
  - `apps/gateway/Dockerfile`
  - `examples/{echo,conformance,oauth-demo}-mcp/Dockerfile`
  - `uv.lock`
  - `CONTRIBUTING.md`, `docs/self-hosting/requirements.md` and `docs/connect/stdio-sidecar.md`
- **Risk:** SQLAlchemy 2.0 → 2.1 is a minor release with deprecations. The hermetic suite, the conformance harness and
  the integration suite exercise it. PyYAML 6.0.3 publishes no 3.15 wheel, so it builds from source. Without libyaml
  headers it builds its pure-Python form, which the image build verifies.
- **Docs:** the three pages above. No ADR: this follows ARC-2's standing rule.
