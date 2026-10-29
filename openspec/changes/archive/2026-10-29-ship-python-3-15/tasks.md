# Tasks

## 1. Declared version, CI and images (ARC-2)

- [x] 1.1 Set `.python-version` to `3.15` and every `python-version` in `.github/workflows/` to `"3.15"`. Move the
  gateway builder to `python:3.15.1-slim-bookworm` (with the pinned uv it already copies) and every Python runtime
  image to `python:3.15.1-slim-bookworm`, `conformance-mcp` included. Verify with
  `test_arc2_images_and_ci_use_the_declared_python` and `test_arc2_every_python_image_names_a_version`
- [x] 1.2 Relock `greenlet`, `cffi`, `markupsafe`, `pydantic`/`pydantic-core`, `sqlalchemy` and `websockets` with
  `uv lock --upgrade-package`, and verify with `uv sync --all-packages --locked` and `uv run pytest -q` on 3.15
- [x] 1.3 Build the gateway image and the example images on 3.15, and verify that the gateway imports its stack
  (`python -c "import sys, yaml, sqlalchemy, bundlemcp"` in the image) and reports ready on 3.15 in CI's integration
  job (the `Shipped gateway runs the declared Python` scenario)

## 2. Documentation

- [x] 2.1 Update `CONTRIBUTING.md`, `docs/self-hosting/requirements.md` and the `docs/connect/stdio-sidecar.md` example
  to 3.15, and verify with `python3 tools/check_docs_links.py` and `uv run rumdl check .`

## 3. Gates

- [x] 3.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`, the four
  `tools/check_*.py` scripts, `python3 tools/check_compose_ports.py`, `python3 tools/check_spec_ids.py` and
  `openspec validate --all --strict`; all pass (no DTO or route changes)
