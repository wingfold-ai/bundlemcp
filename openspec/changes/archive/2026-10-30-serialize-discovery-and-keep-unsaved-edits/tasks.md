# Tasks

## 1. Discoveries of one server do not overlap (UPS-39)

- [x] 1.1 Write hermetic tests that run two `discover()` calls of one server concurrently, on sqlite and on the
  in-memory fakes, with a probe that yields mid-probe; plus one that a discovery of another server is not held up.
  Confirm they fail on `main` (duplicate tool / integrity error) before the fix
- [x] 1.2 Add `UnitOfWork.lock_server` to the application contract; implement it in the SQLAlchemy unit of work
  (Postgres advisory transaction lock, process-local lock on sqlite, released on commit, rollback and close) and in the
  in-memory unit of work (per-server lock owned by the taking task); verify with `uv run lint-imports`
- [x] 1.3 Make the in-memory tool repository refuse a second tool with the same server and name, as the table does;
  verify the 1.1 fake test fails without the lock
- [x] 1.4 Take the lock first thing in `DiscoveryService.discover`; verify the 1.1 tests pass
- [x] 1.5 Add a replica integration test that refreshes one upstream on both replicas at once, and once right after
  the PUT that schedules the background probe, asserting 200s and each tool cached once (`tests/integration`)
- [x] 1.6 Write ADR-0063 and regenerate the ADR indexes (`python3 tools/check_adr_graph.py --fix`); verify
  `check_adr_graph.py` passes

## 2. A colliding write answers 409 (MGMT-6)

- [x] 2.1 Add `StoreConflict` beside `StoreUnavailable`, raise it from the unit-of-work factory for an
  `IntegrityError`, and answer it 409 from a handler registered in `main/app.py`; verify with an infrastructure test
  (duplicate insert through a unit of work raises `StoreConflict`) and an API test (409 problem body, JSON-RPC error
  on an MCP path)

## 3. Unsaved edits survive a refresh (UI-14)

- [x] 3.1 Add `useEditableField` with Vitest cases (keeps an edit across a refetch, follows the gateway when
  untouched, follows again after a save, compares arrays by content); verify they fail against a plain
  watch-and-overwrite and pass with the composable (`npm test`)
- [x] 3.2 Move `BundleMetaCard`, `UpstreamConfigCard`, `UpstreamOAuthCard` and the endpoint detail page onto
  `useEditableField`, clearing transient secret inputs after a successful save; move `MemberEntryCuration` and the
  settings page onto `useEditableRows`; reset `ToolArgumentsEditor` only on a tool name or schema change; verify
  `npm run typecheck` and the Playwright scenarios for these pages
- [x] 3.3 Make E2E-19 wait for the curation save's response before reading the API; add the UI-14 citation to E2E-40
  (refetch after a refused toggle must not undo the typed description) and regenerate the test map
  (`node tests/gen-testmap.mjs`)

## 4. Pausing the live log is final (OPS-15)

- [x] 4.1 Bump the load generation on pause in `logs.vue`; make E2E-36 wait for the filtered backlog response before
  asserting `live`; verify E2E-36 with `--repeat-each 20`

## 5. Verification

- [x] 5.1 Gates: `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`, the
  `tools/check_*.py` scripts (docs links, docs symbols, docs settings, ADR graph, compose ports, spec IDs),
  `bash tests/deploy/test_stack_secrets.sh`, `openspec validate --all --strict`, and in `apps/web`: `npm run openapi`
  (no drift), `npm run typecheck`, `npm run build`, `npm test`
- [x] 5.2 On a local replica stack under its own compose project: `npx playwright test tests/curation.spec.ts
  tests/live-logs.spec.ts --repeat-each 20` with no failure
- [x] 5.3 On the same stack, the CI integration sequence once: demo discovery, `BUNDLEMCP_INTEGRATION=1 uv run pytest
  tests/integration -q -m "not fleet"`, `npx playwright test --grep-invert @fleet`; then tear the stack down
