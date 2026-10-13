# Tasks

## 1. Session timestamps and configurable lifetime

- [ ] 1.1 Add `created_at` and `last_active_at` to `SessionRecord` (described fields with defaults) and verify with a
  unit test citing SES-1 and DEP-6 that a record written without them still loads and the version stays 2
- [ ] 1.2 Add the `SessionLifetime` value object and pass it to `SessionStore.create` and `touch` from `RuntimeConfig`'s
  `session_lifetime`, writing `PERSIST` for `0`; verify with infrastructure tests on fakeredis citing SES-1 and SES-10
  (TTL follows the key, `0` → no TTL, a changed value applies at the next touch)

## 2. Sweeper

- [ ] 2.1 Maintain the activity index in `create`/`touch`/`delete` and add `SessionSweeper` with its Valkey lease;
  verify with tests citing SES-10 that an idle session is removed, its bindings are released through the pool contract
  when it is wired, the expiry is logged, and only one of two instances sweeps
- [ ] 2.2 Start and stop the sweeper from the composition root and verify with an api test that app shutdown stops it
  cleanly

## 3. Graceful shutdown

- [ ] 3.1 Reproduce the current container behaviour (`docker compose stop gateway` timing, shutdown log) and record the
  finding in the PR; change the Dockerfile `CMD` to `exec python main.py` and verify the gateway now logs its shutdown
  and exits before the grace period
- [ ] 3.2 Add `BUNDLEMCP_SHUTDOWN_DRAIN_SECONDS` to `Settings`, pass it to uvicorn as `timeout_graceful_shutdown`, set
  `stop_grace_period` in `deploy/docker-compose.yml`; verify `python3 tools/check_docs_settings.py` after documenting it
  in `docs/self-hosting/configuration.md`
- [ ] 3.3 Implement the shutdown order (readiness 503, refuse new POSTs with 503 + `Retry-After`, end streams, cancel
  calls at the deadline); verify with api tests citing SES-11 that a short call completes during the drain and a long
  one ends with a structured error and `post_call` outcome `cancelled`

## 4. Fail fast without a holder

- [ ] 4.1 Add the `StreamPresence` contract, its Valkey adapter and the in-memory fake; register presence with every
  stream and check it in `ClientRelay._roundtrip`; verify with an api test citing SES-13 that an elicitation for a
  client with no GET stream anywhere fails within a second rather than at the call timeout

## 5. Postgres outage

- [ ] 5.1 Translate connection-level database failures into `StoreUnavailable` in the unit of work and map it to 503
  with `Retry-After` on the MCP edge, `/api/v1` and the OAuth routes; verify with api tests citing SES-14 that a
  `tools/list` with a valid key and a management `PUT` both answer 503, never 401 or 500, and that the size gate still
  answers 413 first
- [ ] 5.2 Update the degradation table in `docs/self-hosting/operations.md` and verify
  `python3 tools/check_docs_links.py` passes

## 6. Caching switch

- [ ] 6.1 Add `BUNDLEMCP_CONFIG_CACHE_DISABLED` to `Settings` and honour it in `RuntimeConfig`; verify with a test
  citing SES-22 that the runtime-config tests pass unchanged with it set, and document it in
  `docs/self-hosting/configuration.md`

## 7. Integration suite

- [ ] 7.1 Add `deploy/docker-compose.replicas.yml` (two gateways behind a round-robin Caddy with `/readyz` health
      checks) and a load-generator helper in `tests/integration/helpers.py`; verify the overlay starts with
      `docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.replicas.yml up --wait`
- [ ] 7.2 Add the SES-12 tests: restart under load, two-replica round-robin, upstream-restart recovery (marked to skip
  until add-upstream-session-pooling's SES-7 has landed); verify they pass against the overlay
- [ ] 7.3 Add the SES-19 tests for endpoint disable, key deactivation and tool disable across the two replicas, each
  asserting the 2-second budget; verify they pass
- [ ] 7.4 Replace the `docker compose restart gateway` test with the DEP-7 rolling update of a newly built image under
  load; verify it passes and that the integration job in `.github/workflows/ci.yml` runs the overlay

## 8. Documentation

- [ ] 8.1 Rewrite `packages/bundlemcp/bundlemcp/api/mcp/README.md` against the current modules (no `composition.py`,
  `streams.py`, `signals.py`, `metering.py`, `upstream.py` or `_drive_upstream`) and the now-working
  `session_lifetime`; verify `python3 tools/check_docs_symbols.py` passes
- [ ] 8.2 Update arc42 §6 (shutdown and sweep runtime scenarios) and §7 (replicas, grace period); verify
  `python3 tools/check_docs_links.py` passes

## 9. Gates

- [ ] 9.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .` and `uv run lint-imports` (delete
  `.import_linter_cache` first) and verify all pass
- [ ] 9.2 Run `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py` and
  `check_adr_graph.py` and verify all pass
- [ ] 9.3 Run `cd apps/web && npm run openapi` if a DTO or route changed and verify the generated files are unchanged
  otherwise
- [ ] 9.4 Run `openspec validate --all --strict` and verify it passes
