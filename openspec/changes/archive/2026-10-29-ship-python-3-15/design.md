# Design

## Context

See [proposal.md](proposal.md). `tests/infrastructure/test_runtime_versions.py` reads `.python-version` and fails on
any image or workflow naming another `X.Y`. The gateway image is two-stage:

- the builder is `ghcr.io/astral-sh/uv:python3.14-bookworm-slim`, with uv 0.13.5 copied over its own;
- the runtime is `python:3.14.9-slim-bookworm`, which receives the builder's `.venv`.

## Goals / Non-Goals

**Goals:**

- One Python minor version everywhere the repository builds or runs Python.
- The `.venv` the builder produces runs on the runtime unchanged, so builder and runtime share interpreter path, ABI
  and glibc.

**Non-Goals:**

- Raising `requires-python`. 3.13 and 3.14 stay supported for running outside a container.
- Upgrading dependencies beyond what 3.15 needs. A wider refresh stays with Dependabot.

## Decisions

### Build on `python:3.15-slim-bookworm` and copy uv in

`astral-sh/uv` publishes `python3.15-trixie-slim` but no bookworm image for 3.15. A trixie builder would compile
against glibc 2.41, and its `.venv` would then run on bookworm's 2.36. Building on the runtime's own base removes that
whole class of mismatch. The builder already copies `uv` from `ghcr.io/astral-sh/uv:0.13.5`, so nothing else changes.

The runtime is pinned to the patch release `python:3.15.1-slim-bookworm`, as before. The builder uses the same pin, so
both stages move together when Dependabot bumps them.

### Upgrade only the packages 3.15 needs

The packages are moved with `uv lock --upgrade-package` for `greenlet`, `cffi`, `markupsafe`, `pydantic-core` (with
its matching `pydantic`), `sqlalchemy` and `websockets`. Each either lacked a 3.15 wheel at its locked version or, like
greenlet, failed at runtime on 3.15.

## Risks / Trade-offs

- [SQLAlchemy 2.1 changes behaviour the repositories rely on] → the full hermetic suite passed on 3.15 with 2.1.6
  (1234 passed before the version files moved). The integration suite runs on the compose stack in CI.
- [PyYAML has no 3.15 wheel and the slim builder has no compiler] → PyYAML falls back to its pure-Python build when
  libyaml is absent. The image build in CI proves it, and the bootstrap loader is the only user.
- [Local development on 3.14] → `requires-python` still allows it, and uv picks the declared 3.15 by default.

## Migration Plan

Merge, then rebuild images. Rollback is the previous image tag. The database is untouched.
