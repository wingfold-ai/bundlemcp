# 50 — Audit log

**Status:** Accepted · **Origin:** metamcp carry-over (fork feature) **Prior art:**
`../metamcp/apps/backend/src/lib/metamcp/metamcp-middleware/audit-requests.functional.ts`, `mcp_request_audit_logs`
table

## Summary

An append-only Postgres record of every tool call through every endpoint: who called what, where it went, how long it
took, how it ended. The primary answer to "what happened?", and the reconciliation source for an application layer's
billing.

## Requirements

- **AUD-1** One record per `tools/call`, written by the audit middleware ([MID-2](31-middleware.md)) after completion:
  endpoint, bundle, server, original + presented tool name, caller (`user_id`/`api_key_id`, auth method), session id,
  `status` (`success`|`error`|`denied`), `duration_ms`, truncated `error_message`, timestamp. Identifiers as nullable
  FKs + denormalized names ([DOM-2](02-domain-model.md)).
- **AUD-2** Denied calls (disabled tool, metering deny, auth-ok-but-forbidden) are audited with `status=denied` and the
  reason; auth failures and rate-limit rejections are NOT audit records ([RATE-3](16-rate-limiting.md)) — they go to
  logs/metrics.
- **AUD-3** Writing is async/fire-and-forget relative to the client response (never adds latency, never fails a call),
  but MUST be durable under normal operation (bounded in-process queue flushed to Postgres; queue overflow is a metric +
  log, not silent loss).
- **AUD-4** Tool call **arguments and results are not stored** in v1 (privacy
  + size); a per-endpoint opt-in flag MAY add truncated argument capture
  later.
- **AUD-5** Retention: runtime-configurable (`Config`) age-based purge job, default 90 days.
- **AUD-6** UI page with filters (time range, endpoint, bundle, server, tool, caller, status) and CSV export; same
  filters on `GET /api/v1/audit-records` ([API-5](40-management-api.md)).
- **AUD-7** The audit log is the metering **reconciliation source** ([MID-3](31-middleware.md)): for every invocation
  whose pre-call hook succeeded, an audit record with a terminal status MUST eventually exist (or the invocation is
  identifiable as lost) — this is what lets a billing consumer detect debits that never completed.

## Out of scope

- Shipping audit data to external SIEMs (operators can read the table or poll the API).

## Open questions

- None.
