# Proposal: harden the audit log

## Why

The audit log is the metering reconciliation source, but it cannot yet carry that weight: a failed Postgres write is
logged and the record dropped; an overflow is only a log line and an attribute nothing exports; nothing on an audit
record links it to the metering debit it settles, so consumers reconcile on `(sub, tool_name, created_at)` and accept
ambiguity (`docs/integrate/metering-hook.md`); and nothing purges the table although `audit_retention_days` has been in
the runtime config since the start. On the reading side the UI filters only by endpoint, status, tool and time, and its
CSV export contains the 100 loaded rows rather than the filtered result. A valid credential used on an endpoint it is
not entitled to is answered at admission and leaves no audit trace at all.

## What Changes

- **OPS-2:** a `tools/call` whose credential is valid but not entitled to the endpoint is audited as `denied`
  (`forbidden`); auth failures and rate-limit rejections stay out of the audit log and go to logs **and metrics**.
- **OPS-3:** a failed write is retried rather than dropped; overflow and finally-failed writes are a metric plus a log
  line that names the record's idempotency key; the queue drains on shutdown within a bounded time.
- **OPS-5:** a purge job deletes records older than `audit_retention_days` (default 90; `0` keeps everything), one
  replica at a time.
- **OPS-6:** the UI filters by bundle, server and caller too; CSV export covers the whole filtered result, caller
  columns included, through a server-side export route with the list's filters.
- **OPS-7:** every audit record of a metered invocation carries the invocation's idempotency key, and an invocation
  whose record cannot be written is identifiable as lost by that key in the logs.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `operations`: MODIFIED OPS-2, OPS-3, OPS-5, OPS-6, OPS-7.

## Impact

- **Depends on** [add-prometheus-metrics](../add-prometheus-metrics/proposal.md): the overflow, failed-write and
  rejection metrics are recorded through its metrics contract and exported on its `/metrics` route. Land it first.
- **Schema:** a nullable `idempotency_key` column (indexed) on `audit_records` — expand-only migration (DEP-5).
- **API:** `AuditRecordRead` gains `idempotency_key`; `AuditFilter` gains `idempotency_key`; new route
  `GET /api/v1/audit-records:export` (CSV, same filters). `apps/web/openapi.json` and `types/api.d.ts` regenerate.
- **Metering contract:** no change to `METERING_PROTOCOL_VERSION` — the key the hook already receives is now also on the
  audit record. `docs/integrate/metering-hook.md` "Crash reconciliation" is rewritten to reconcile by key.
- **UI:** `apps/web/app/pages/audit.vue` (filters, export). The admin-ui UI-1 wording for the audit page is owned by
  [complete-admin-ui](../complete-admin-ui/proposal.md), which depends on this change.
- **Code:** `infrastructure/postgres/audit_writer.py`, the MCP admission path, a new purge job beside `api/jobs/`
  `token_purger.py`, `application/management/audit_service.py`.
- **Interaction:** [align-metering-contract](../align-metering-contract/proposal.md) decides whether `pre_call` may
  repeat under one key (PROT-26); this change records the key either way, and OPS-7 is stated per invocation, not per
  pre-call.
- **ADR:** one ADR (next free number) on audit durability and the idempotency key as the reconciliation join.
