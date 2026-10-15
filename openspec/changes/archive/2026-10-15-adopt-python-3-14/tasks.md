# Tasks

## 1. Declared version and its test

- [x] 1.1 Add `.python-version` (`3.14`) at the repository root and
  `packages/bundlemcp/tests/infrastructure/test_runtime_versions.py`, citing ARC-2, that compares it with the Python
  version of every Dockerfile under `apps/` and `examples/` and every `python-version:` in `.github/workflows/*.yml`.
  Verify the test fails on the current tree and names all seven references.

## 2. Images and CI on 3.14

- [x] 2.1 Move both stages of `apps/gateway/Dockerfile`, `examples/echo-mcp/Dockerfile` and
  `examples/oauth-demo-mcp/Dockerfile` to 3.14, and the three `python-version` inputs in `.github/workflows/ci.yml`.
  Verify the ARC-2 test passes and `uv run pytest -q` passes on 3.14.
- [x] 2.2 Rebuild the compose stack and verify the gateway reports ready on Python 3.14
  (`docker exec deploy-gateway-1 python --version`), the integration suite passes
  (`BUNDLEMCP_INTEGRATION=1 uv run pytest tests/integration -m "not fleet"`) and `npx playwright test` passes.
- [x] 2.3 In `.github/dependabot.yml`, add `examples/oauth-demo-mcp` to the Docker directories and group the Python base
      images. Verify the file still parses (`python3 -c "import yaml; yaml.safe_load(open('.github/dependabot.yml'))"`).
- [x] 2.4 Update the `FROM python:3.13-slim` example in `docs/connect/stdio-sidecar.md`. Verify
      `python3 tools/check_docs_links.py` passes and that a search for `python:3.13` and `python3.13` in Dockerfiles,
      workflows and Markdown (excluding `node_modules` and archived changes) finds nothing outside this change.

## 3. The open release-engineering change

- [x] 3.1 In `openspec/changes/complete-release-engineering`, remove the Python open decision from `proposal.md`,
  rewrite the ARC-2 delta to this change's Python text and scenarios plus its Node text, and remove task 1.1, task 2.3
  and the Python half of task 2.4, pointing at this change. Verify `openspec validate complete-release-engineering
  --strict` passes.

## 4. Gates

- [x] 4.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`,
  `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py`, `check_adr_graph.py`,
  `python3 tools/check_spec_ids.py` and `openspec validate --all --strict`; confirm each is clean.
