# Tasks

## 1. Idempotency key on the record (OPS-7)

- [x] 1.1 Add `idempotency_key` to `AuditRecord`, the row class and an expand-only Alembic migration with an index;
  verify `alembic upgrade head` and `downgrade -1` succeed against the compose Postgres
- [x] 1.2 Stamp the key from `ToolCall` through `AuditContext` on every record it writes (terminal, `input_required`,
  resumed); verify `test_ops7_record_carries_idempotency_key` and `test_ops7_resumed_call_keeps_key`
- [x] 1.3 Add the field to `AuditRecordRead` and `AuditFilter`; verify `test_ops7_list_filters_by_idempotency_key` and
  regenerate with `cd apps/web && npm run openapi`
- [x] 1.4 Rewrite "Crash reconciliation" in `docs/integrate/metering-hook.md` to join on `idempotency_key` and add the
  field to `docs/manage/audit.md`; verify `python3 tools/check_docs_links.py`

## 2. Durable writing (OPS-3)

- [x] 2.1 Batch the drain loop and retry a failed batch with backoff for 60 s before giving up with
  `audit.write_failed` per record (key included) and the failed-write metric; verify
  `test_ops3_transient_failure_is_retried` and `test_ops3_persistent_failure_logged_with_key`
- [x] 2.2 Log overflow with the dropped record's key and record the overflow metric; verify
  `test_ops3_overflow_logged_with_key_and_counted` and `test_ops3_overflow_logged_with_key_and_counted (OPS-7)`
- [x] 2.3 Bound the shutdown drain (10 s) and log `audit.lost_on_shutdown` per remaining record; verify
  `test_ops3_shutdown_drains_queue` and `test_ops3_drain_deadline_names_lost_records`
- [x] 2.4 Correct the writer's docstrings and the durability paragraph of `docs/manage/audit.md`; verify
  `python3 tools/check_docs_symbols.py`

## 3. Forbidden calls are audited (OPS-2)

- [x] 3.1 Introduce the authenticator result (authenticated / forbidden / not authenticated) and return forbidden from
  the API-key and OAuth-bearer authenticators for valid credentials not entitled to the endpoint; verify the existing
  admission tests still pass with unchanged status codes
- [x] 3.2 Submit a `denied`/`forbidden` record from `AdmissionGate` for `tools/call` only; verify
  `test_ops2_valid_key_wrong_endpoint_audited_forbidden` and `test_ops2_forbidden_tools_list_not_audited`
- [x] 3.3 Verify `test_ops2_rate_limited_call_counted_not_audited` and `test_ops2_auth_failure_counted_not_audited`
  against the metrics fake
- [x] 3.4 Document the `forbidden` reason in `docs/manage/audit.md` and verify the docs build

## 4. Retention purge (OPS-5)

- [x] 4.1 Add `AuditRetentionService.purge_older_than` and the repository delete (chunked) with its memory fake; verify
  `test_ops5_old_records_purged` and `test_ops5_zero_keeps_everything`
- [x] 4.2 Add `AuditPurger` with a Valkey lease, reading `audit_retention_days` each run, and start/stop it in the
  composition root; verify `test_ops5_retention_change_applies_without_restart` and
  `test_ops5_one_replica_purges_per_interval`
- [x] 4.3 Replace the "nothing purges" warnings in `docs/manage/audit.md`, `docs/self-hosting/operations.md`,
  `requirements.md`, `configuration.md` and `deploy.md`'s checklist; verify `python3 tools/check_docs_settings.py`

## 5. Querying and export (OPS-6)

- [x] 5.1 Add `AuditService.export` and `GET /api/v1/audit-records:export` (streamed CSV, same filters, caller and key
  columns); verify `test_ops6_export_applies_list_filters` and `test_ops6_export_streams_whole_result`
- [x] 5.2 Add bundle, server and caller (user / API key) filters to `apps/web/app/pages/audit.vue` and switch
  "Export CSV" to the export route; verify a Playwright test `OPS-6 filters by bundle, server and caller` and
  `OPS-6 CSV export covers the filtered result` against the demo seed, and `npm run typecheck`
- [x] 5.3 Update `docs/manage/audit.md` (export route, UI filters) and regenerate the OpenAPI types with
  `cd apps/web && npm run openapi`

## 6. Architecture records

- [x] 6.1 Write the ADR (audit durability, idempotency key as reconciliation join, purge lease) as the next free number
  in `docs/adr/`, index it, update arc42 §8 and §11 (remove the closed debt items); verify
  `python3 tools/check_adr_graph.py`

## 7. Gates

- [x] 7.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports` and verify all
  pass
- [x] 7.2 Run `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py`,
  `check_adr_graph.py` and verify all pass
- [x] 7.3 Run `cd apps/web && npm run openapi` and verify `apps/web/openapi.json` and `types/api.d.ts` are committed and
  current; run `npm run typecheck`
- [x] 7.4 Run `openspec validate --all --strict` and verify it passes
