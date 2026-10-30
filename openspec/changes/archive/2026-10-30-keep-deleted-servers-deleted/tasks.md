# Tasks

## 1. A deleted server stays deleted (UPS-40)

- [x] 1.1 Write hermetic tests, confirmed failing on `main`: on the in-memory fakes, a delete through `ServerService`
  during a stalled probe waits for the discovery and leaves the server deleted, and a server removed from the store
  behind the lock's back during a stalled probe stays removed with no tool stored; on sqlite, the same two plus a rename
  during a stalled probe that the discovery keeps
- [x] 1.2 Add `ServerObservations` (domain) and `McpServer.observations`; add `ServerRepository.record_observations`
  (application contract) with its SQLAlchemy adapter (an update that never inserts) and in-memory fake; verify with
  `uv run lint-imports`
- [x] 1.3 Record observations instead of staging the server in every `DiscoveryService.discover` path, before any tool,
  entry or listing is staged, and report "server not found" when nothing was recorded; do the same in
  `UpstreamHealth.failed`/`succeeded`; verify the removal and rename tests of 1.1 pass
- [x] 1.4 Take the server lock in `ServerService.delete` before deleting; verify the delete tests of 1.1 pass
- [x] 1.5 Add a replica integration test that deletes an upstream through one replica while a refresh of it runs on
  the other, and asserts it stays deleted (`tests/integration/test_replicas.py`)
- [x] 1.6 Write ADR-0064 amending ADR-0063, add the back-pointer to ADR-0063, regenerate the indexes
  (`python3 tools/check_adr_graph.py --fix`); verify `check_adr_graph.py` passes
- [x] 1.7 Document in `docs/manage/servers.md` (Deleting; Tools and health) that a delete waits for a discovery in
  flight and that a discovery never undoes a change saved meanwhile; verify `check_docs_links.py` and
  `check_docs_symbols.py`

## 2. Verification

- [x] 2.1 Gates: `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`, the
  `tools/check_*.py` scripts (docs links, docs symbols, docs settings, ADR graph, compose ports, spec IDs),
  `bash tests/deploy/test_stack_secrets.sh`, `openspec validate --all --strict`, and `cd apps/web && npm run openapi`
  (no drift)
- [x] 2.2 On a local replica stack under its own compose project: `npx playwright test tests/server-flow.spec.ts
  --repeat-each 20` with no failure
- [x] 2.3 On the same stack, the CI integration sequence once: demo discovery, `BUNDLEMCP_INTEGRATION=1 uv run pytest
  tests/integration -q -m "not fleet"`, `npx playwright test --grep-invert @fleet`; then tear the stack down
