# Tasks

## 1. Buffer contract and adapters

- [ ] 1.1 Add the `LiveLogEntry` model and the `LiveLogBuffer` contract in `application/contracts/live_state/`, a
  memory fake in `infrastructure/memory/`, and the Valkey stream adapter in `infrastructure/valkey/` (capped append,
  backfill, follow from a cursor); verify with fakeredis tests that the stream is capped near 10,000 entries and that
  follow returns entries after a cursor in order (OPS-14, OPS-16)
- [ ] 1.2 Verify `uv run lint-imports` passes with the contract importing no driver

## 2. Publishing log events

- [ ] 2.1 Add `BUNDLEMCP_LIVE_LOG_LEVEL` to `Settings` with a described, pattern-constrained field and document it in
  `docs/self-hosting/configuration.md`; verify `python3 tools/check_docs_settings.py` passes
- [ ] 2.2 Add the live-log handler beside the stderr handler with its own threshold and a bounded queue, and the
  background publisher draining it in batches with the replica id; verify with tests that an event below the threshold
  is not published, that a full queue drops instead of blocking, and that a store outage leaves the request and the
  process log unaffected (OPS-14)
- [ ] 2.3 Verify with a test that the buffer entry for a request carrying an API key and an `Authorization` header holds
  neither, and equals the process log line's fields (OPS-17)
- [ ] 2.4 Start and stop the publisher in the composition root (`main/`) with the other Valkey background tasks; verify
  with an API-level test that an event logged during a request reaches the memory fake (ARC-8)

## 3. Management API

- [ ] 3.1 Add `LiveLogService` (level, free-text, upstream, endpoint filters) in `application/` and the live-log
  controller with a backfill route and an SSE route honouring `Last-Event-ID`; verify with ASGI tests for filtering,
  resume without duplicates, and refusal without credentials (OPS-15)
- [ ] 3.2 Cap concurrent streams per replica and answer `429` beyond it; verify with a test
- [ ] 3.3 Run `cd apps/web && npm run openapi` and verify the generated files are current

## 4. Admin UI and docs

- [ ] 4.1 Replace the placeholder in `apps/web/app/pages/logs.vue` with the live tail, pause/resume, level and text
  filters, and upstream/endpoint pickers; update `apps/web/tests/login.spec.ts` to assert the real page and add a
  Playwright test citing OPS-15 for pause/resume; verify `npm run typecheck` and the UI suite pass
- [ ] 4.2 Document the page in `docs/self-hosting/operations.md` (replacing "no live log stream"), stating that the
      buffer is ephemeral and what to use for history; update arc42 §5/§8 and the LikeC4 model if the Valkey contents
      are drawn there; verify `npx likec4 validate docs/likec4` and the docs checks pass
- [ ] 4.3 Add the ADR for log fan-out through a capped Valkey stream; verify `python3 tools/check_adr_graph.py` passes

## 5. Gates

- [ ] 5.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`, the four
  `tools/check_*.py` scripts, `cd apps/web && npm run openapi`, and `openspec validate --all --strict`; verify all pass
