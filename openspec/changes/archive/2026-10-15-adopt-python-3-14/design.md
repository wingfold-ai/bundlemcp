# Design

## Context

Python versions are named in seven places today, none of them derived from another: the two stages of
`apps/gateway/Dockerfile` (a `ghcr.io/astral-sh/uv:python3.13-bookworm-slim` builder that creates the virtualenv, and a
`python:3.13-slim-bookworm` runtime that copies it), the `FROM` lines of `examples/echo-mcp` and
`examples/oauth-demo-mcp`, and three `python-version: "3.13"` inputs in `.github/workflows/ci.yml`. The virtualenv
holds compiled wheels and an interpreter path for the builder's Python, so builder and runtime must agree; #114 broke
exactly that. Dependabot watches `apps/gateway`, `apps/web` and `examples/echo-mcp` as separate Docker directories, so
it proposes one bump per file and misses `examples/oauth-demo-mcp`.

## Goals / Non-Goals

**Goals:**

- One declared shipped version, checked against every image and CI job by a test in the hermetic suite.
- Future Python bumps arrive as one Dependabot pull request that passes or fails as a whole.

**Non-Goals:**

- Raising the supported minimum: `requires-python` stays `>=3.13`.
- CI on several Python versions. The shipped version is the one tested; a 3.13 matrix job is not added.
- The Node half of ARC-2, which stays in `complete-release-engineering`.

## Decisions

**`.python-version` is the declaration.** A one-line `3.14` file at the repository root. uv already reads it, so
`uv sync` and `uv run` use 3.14 locally without further configuration, and it is the conventional file other tools
recognise. Alternatives: a `[tool.bundlemcp]` key in `pyproject.toml` (nothing reads it but the test), or the CI
workflow as the source (a YAML file the Dockerfiles cannot point at either). The Dockerfiles and the workflow still
spell the version literally, because a `FROM` line cannot read a file; the test is what ties them together.

**The test lives with the hermetic suite** (`packages/bundlemcp/tests/infrastructure/test_runtime_versions.py`, next
to the seed tests that already read `deploy/`). It parses `.python-version`, then every `Dockerfile` under `apps/` and
`examples/` (the Python version in a `python:<v>` or `uv:python<v>` image reference) and every `python-version:` input
in `.github/workflows/*.yml`, and fails naming each file and version that differs. It also fails when it finds no
reference at all in a file it expects one in, so a renamed image cannot silence it. It runs in the existing backend job;
no new CI job.

**ruff's `target-version` stays `py313`.** It names the oldest Python the code must parse on. Moving it to `py314`, as
`complete-release-engineering` task 2.3 proposed, would let 3.14-only syntax into a library that still declares 3.13
support.

**Dependabot groups the Docker updates.** The `docker` entry gains `examples/oauth-demo-mcp` and a group for the Python
base images (`python` and `astral-sh/uv`), so a bump touches every Dockerfile in one pull request and the test above
judges the result. Whether Dependabot parses the `uv:python3.14-bookworm-slim` tag is not certain; if it does not, the
`python:` images still move together and the test fails the pull request until the builder is bumped by hand.

**`complete-release-engineering` is edited, not left to conflict.** Its ARC-2 delta is a MODIFIED block of the whole
requirement, so archiving it after this change would overwrite the text below. Its delta is rewritten to this change's
Python text plus its own Node text and scenarios; its open decision, task 1.1, the Python half of task 2.4 and task 2.3
are removed, pointing here.

## Risks / Trade-offs

- [A dependency has no 3.14 wheel, or behaves differently on 3.14] → The locked set already installs and the full suite
  passes on 3.14 (verified while preparing this change); the integration suite runs against the rebuilt images before
  merge.
- [Contributors' local `.venv` silently switches to 3.14] → uv recreates it on the next `uv sync`; noted in the PR.
  Anyone without 3.14 installed gets it from uv's managed Pythons.
- [3.13 support is claimed but no longer tested] → Accepted: the declared minimum is a compatibility promise for the
  library, kept honest by ruff's `py313` target. A 3.13 job can be added if a consumer depends on it.

## Migration Plan

Deploy the new images as usual; nothing is stored differently and no migration runs for this change. Rolling back is
deploying the previous image.
