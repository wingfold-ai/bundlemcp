# Design: harden the audit log

## Context

See [proposal.md](proposal.md) for the motivation. Today:

- `infrastructure/postgres/audit_writer.py::QueuedAuditWriter` holds an `asyncio.Queue(maxsize=1000)`; `record()` drops
  on `QueueFull` (`self.dropped += 1`, `audit.queue_overflow`); `_drain()` writes one row per record and on any
  exception logs `audit.write_failed` and moves on. `stop()` awaits `queue.join()` with no deadline — if Postgres is
  down at shutdown it never returns until the orchestrator kills the process.
- `ToolCall` (`api/mcp/tool_call/tool_call.py`) creates the idempotency key in its constructor (or carries it over for a
  resumed MRTR call) and passes it in `MeterContext`; `AuditContext.record(...)` builds the `AuditRecord`, which has no
  key field.
- `AdmissionGate.admit_caller` authenticates via `EndpointAuthentication`; `ApiKeyAuthenticator` returns `None` both for
  an unknown key and for a valid key that does not reach the endpoint (`key.reaches(endpoint_id)`), so the two are
  indistinguishable and neither is audited. `OAuthBearerAuthenticator` behaves the same for an audience mismatch.
- `api/jobs/token_purger.py` is the pattern for a periodic purge; `api/jobs/tool_refresher.py` adds a Valkey lease so
  one replica sweeps per interval.
- `audit_retention_days` is registered in `domain/config/config_registry.py` and read by nothing.

## Goals / Non-Goals

**Goals:**

- No record lost to a transient Postgres blip; every loss that remains is named by its idempotency key.
- A join key between the metering ledger and the audit log.
- Retention that is applied, not advisory.

**Non-Goals:**

- A durable outbox (Valkey stream or Postgres-first write). A process killed with `SIGKILL` still loses its in-memory
  queue; the key in the pre-call is what lets a consumer detect that (the "identifiable as lost" half of OPS-7).
- Changing the status codes of refused requests (EP-3a in
  [complete-oauth-server](../archive/2026-10-15-complete-oauth-server/proposal.md) owns those).
- Argument capture (OPS-4 stays as is).

## Decisions

### D1. Retry inside the writer, with a bounded retry budget and batching

The drain loop takes up to 100 queued records per transaction. On a write error it retries the same batch with
exponential backoff (0.5 s doubling to 8 s, jitter) until 60 s have passed, then logs `audit.write_failed` once per
record with its idempotency key, records the failed-write metric and continues. While retrying, new records keep
queueing; if the queue fills, overflow applies (D2).

- *Why batching:* it lets the writer catch up after an outage instead of trailing it by one round-trip per record.
- *Alternative:* re-enqueue failed records at the tail. Rejected: it reorders records and can starve the queue of space
  during a long outage, turning one failure into overflows of newer records.
- *Alternative:* spill to Valkey on failure. Rejected for this change (a second durable path to reason about); listed
  as a later option in the ADR.

### D2. Overflow keeps its policy, gains a key and a metric

On `QueueFull` the **new** record is dropped (as today), logged as `audit.queue_overflow` with `idempotency_key`,
`endpoint_name`, `presented_tool_name` and `status`, and counted via the metrics contract of
[add-prometheus-metrics](../add-prometheus-metrics/proposal.md) (`audit_dropped(reason="overflow")`). The queue depth
gauge is that change's.

### D3. Bounded drain on shutdown

`stop(deadline=10 s)` waits for the queue to empty or the deadline; then cancels the drain task and logs every record
still in the queue (and the batch in flight) as `audit.lost_on_shutdown` with its key. The deadline is a module
constant sized to fit inside the gateway's graceful-shutdown window (SES-11 in
[complete-session-lifecycle](../archive/2026-10-16-complete-session-lifecycle/proposal.md)).

### D4. The idempotency key on the record

- `domain/audit/audit_record.py`: `idempotency_key: str | None` (described; `None` for denials before a `ToolCall`
  exists — unknown tool, forbidden caller).
- `infrastructure/postgres/rows/audit_record_row.py` and an expand-only Alembic migration adding a nullable indexed
  column.
- `AuditContext` is given the key by `ToolCall` and stamps every record it writes, including the `input_required`
  intermediate record and the resumed call's terminal record (same key).
- `AuditFilter`, `AuditRecordRead` (`application/schemas/`) gain the field; OpenAPI regenerates.

### D5. Forbidden is distinguishable from unauthenticated

Authenticators return a small result model (`application/` or `api/mcp/routing/authentication/`, API layer only):
`Authenticated(identity)`, `Forbidden(identity, reason)` or `NotAuthenticated`. `ApiKeyAuthenticator` returns
`Forbidden` for a valid key that does not reach the endpoint; `OAuthBearerAuthenticator` for a valid token whose
audience is another endpoint. `AdmissionGate` keeps the current response for both (so no status code changes here) and,
when the parsed message is `tools/call`, submits a `denied`/`forbidden` audit record with the endpoint, bundle, caller
ids and the presented tool name from `params.name` — no database write in the request path (the writer is async).

- Whether a forbidden attempt still counts toward the auth-failure lockout is unchanged by this change (it does today);
  see Open Questions.
- *Alternative:* audit in the tools/call handler. Not possible: a forbidden caller never reaches dispatch.

### D6. Purge job

`api/jobs/audit_purger.py::AuditPurger`, beside `TokenPurger`, runs every 15 min, takes a Valkey lease
(`bundlemcp:audit:purge`, the `RefreshLock` contract) so one replica purges per interval, reads `audit_retention_days`
through `RuntimeConfig` each run, and calls `AuditRetentionService.purge_older_than(days)` (`application/management/`),
which deletes through the audit repository in chunks of 10 000 rows to keep transactions short. `0` skips. Logs
`audit.purged` with the count.

### D7. Server-side CSV export

`AuditController` gains `@route.get(":export")` returning a `StreamingResponse` (`text/csv`), with the same
`AuditFilterQuery`; `AuditService.export(filter_)` yields rows newest first in pages of 500 so memory stays flat. The
UI's "Export CSV" downloads from that route with the current filters (a link with the admin cookie; `GET` needs no CSRF
origin check). The route is declared before any parameterised sibling.

- *Alternative:* page through the list API in the browser. Rejected: slow for large results, and the CSV columns would
  live in two places.

### D8. Layers

| Piece | Layer |
|---|---|
| `AuditRecord.idempotency_key` | `domain/audit/` |
| `AuditRetentionService`, `AuditService.export`, filter field | `application/management/` |
| Row column, migration, writer retry/drain | `infrastructure/postgres/` |
| Authenticator result, admission audit, purge job, export route | `api/` |
| Wiring | `main/` |

## Risks / Trade-offs

- [A long outage still drops records] → bounded by design; every drop names its key, and the metric alerts.
- [Purge deletes evidence a consumer still needs] → documented: retention must exceed the reconciliation window;
  `0` disables.
- [Large `DELETE` locks] → chunked deletes; index on `created_at` exists for the list ordering (verify, add if not).
- [Audit rows for forbidden attempts can be used to fill the table] → only for valid credentials, and rate limits apply
  per caller; a scanning attacker with invalid credentials produces no rows.

## Migration Plan

Expand-only migration (nullable column + index), safe one release back (DEP-5). Old records have no key. Rollback:
previous image ignores the column.

## Open Questions

- Should a forbidden-but-valid credential stop counting toward the auth-failure lockout? Deferrable: it does not change
  the audit behaviour specified here.
