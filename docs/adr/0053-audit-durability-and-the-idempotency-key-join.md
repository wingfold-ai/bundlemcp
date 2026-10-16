# ADR-0053: The audit log is written durably, names every loss by idempotency key, and is purged by retention

**Status:** accepted · **Date:** 2026-10-16

## Context

The audit log is the metering reconciliation source, but it could not carry that weight. A failed Postgres write was
logged and the record dropped; an overflow was a log line and an attribute nothing exported; no audit record linked
to the metering debit it settled, so a consumer reconciled on `(sub, tool_name, created_at)` and accepted ambiguity;
nothing applied `audit_retention_days`; and a valid credential used on an endpoint it was not entitled to left no trace.

## Decision drivers

- No record lost to a transient Postgres blip.
- Every loss that remains is identifiable by the invocation it belonged to.
- A join key between a metering ledger and the audit log, the same on every leg of an invocation.
- Retention applied by the gateway, not left to the operator.
- The write stays off the request path: it never adds latency and never fails a call.

## Decision

- **The idempotency key is on the record.** Every leg the stage chain settles carries the invocation's metering
  idempotency key, so a ledger joins on it; `GET /api/v1/audit-records` filters by it. A call denied before metering
  has none.
- **The writer batches and retries.** Up to 100 records per transaction; a failed batch is retried with exponential
  backoff for 60 seconds before its records are given up. The bounded queue (1000) keeps its policy: a record
  submitted to a full queue is the one dropped.
- **Every loss is named and counted.** An overflow, a given-up write and a record left when the 10-second shutdown
  drain runs out are each logged (`audit.queue_overflow`, `audit.write_failed`, `audit.lost_on_shutdown`) with the
  record's idempotency key, and counted in `bundlemcp_audit_dropped_total` by reason.
- **A purge job applies retention**, every 15 minutes on one replica under a Valkey lease, reading
  `audit_retention_days` on every run and deleting in chunks of 10 000; `0` keeps everything.
- **A valid credential not entitled to the endpoint** is told apart from no credential by the authenticators, and a
  `tools/call` refused that way is audited as `denied`, `forbidden`. The answer is unchanged.
- **The export streams the whole filtered result** from a keyset walk, a page per short transaction, so neither
  memory nor a transaction grows with the result.

## Alternatives considered

- **A durable outbox** (a Valkey stream, or writing to Postgres first). It would survive `SIGKILL`, but adds a second
  durable path to reason about; the key in the pre-call already lets a ledger detect that loss.
- **Re-enqueue a failed record at the tail.** It reorders records and, during a long outage, crowds newer records out
  of the queue.
- **Reconcile by time window.** Ambiguous for two calls in the same instant, which is exactly what a retry produces.
- **Page the export with offsets.** Records written during a long export would repeat or skip a row.

## Consequences

### Positive

- A metering ledger reconciles by key, and knows which invocations an outage cost.
- The audit table no longer grows without bound.

### Trade-offs

- A process killed outright still loses its in-memory queue; only the pre-call's key reveals it.
- Purging removes evidence a consumer may still want; the retention must exceed the reconciliation window.
- Audit rows for forbidden attempts can be produced only with valid credentials, and rate limits apply to them.
