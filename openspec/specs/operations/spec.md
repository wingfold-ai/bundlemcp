# operations Specification

## Purpose

What operators see while the gateway runs. The append-only audit log: one record per tool call (who, what, where, how
long, how it ended), denied calls included, never arguments or results, written asynchronously without slowing calls,
queryable through the API and UI, and the reconciliation source for an application layer's billing. Structured logs and
the health and readiness probes for orchestrators. Metrics, tracing and the live log view will live here once built.

Rate-limit and lockout counters are specified with their limiters in the endpoints slice.

It merges what were separate specs until 2026-10-13: Audit log, Observability.

## Requirements

### Requirement: OPS-1 One record per tool call
The gateway SHALL write one audit record per `tools/call`, after completion, from the tool-call pipeline
([PROT-25](../protocol/spec.md)): endpoint, bundle, server, original + presented tool name, caller
(`user_id`/`api_key_id`, auth method), session id, `status` (`success`|`error`|`denied`), `duration_ms`, truncated
`error_message`, timestamp. Identifiers SHALL be nullable FKs + denormalized names ([ARC-17](../architecture/spec.md)).

#### Scenario: Successful call is recorded
- **WHEN** a client calls `echo__say` on endpoint `main` and the upstream answers
- **THEN** one record exists with status `success`, endpoint `main`, server `echo`, tool `say`, and a `duration_ms`

#### Scenario: Long upstream error is truncated
- **WHEN** an upstream call fails with an exception message longer than 500 characters
- **THEN** the record's `error_message` holds at most the first 500 characters

### Requirement: OPS-2 Denied calls are audited
Denied calls (disabled or unknown tool, metering deny) SHALL be audited with `status=denied` and the reason; auth
failures and rate-limit rejections SHALL NOT be audit records ([EP-18](../endpoints/spec.md)) — they go to logs.

#### Scenario: Metering denies a call
- **WHEN** the metering hook denies a call with reason `insufficient_credits`
- **THEN** a record with status `denied` and `denied_reason` `insufficient_credits` is written

#### Scenario: Disabled tool
- **WHEN** a client calls a tool that is disabled in the bundle
- **THEN** a record with status `denied` and reason `unknown_or_disabled_tool` is written

#### Scenario: Rate-limited call
- **WHEN** a call is rejected by a rate limit
- **THEN** no audit record is written for it

### Requirement: OPS-3 Asynchronous, bounded writing
Writing SHALL be async/fire-and-forget relative to the client response (never adds latency, never fails a call), via a
bounded in-process queue (1000 records) flushed to Postgres and drained on shutdown. Queue overflow SHALL be counted and
logged as `audit.queue_overflow`, not lost silently; a failed write SHALL be logged as `audit.write_failed`.

#### Scenario: Response does not wait for the write
- **WHEN** a tool call completes
- **THEN** the response is returned without waiting for the audit row to be committed

#### Scenario: Queue overflow
- **GIVEN** the audit queue holds 1000 pending records
- **WHEN** another record is submitted
- **THEN** the call is unaffected, the drop counter increases, and a warning `audit.queue_overflow` is logged

### Requirement: OPS-4 No arguments or results
Tool call **arguments and results SHALL NOT be stored** (privacy + size).

#### Scenario: Arguments are not persisted
- **WHEN** a client calls a tool with arguments `{"text": "secret"}`
- **THEN** the audit record contains neither the arguments nor the result

### Requirement: OPS-5 Retention setting
The runtime configuration (`Config`) SHALL carry the key `audit_retention_days`, default 90, as the intended
age-based retention of audit records.

#### Scenario: Default retention value
- **WHEN** no override is stored for `audit_retention_days`
- **THEN** `GET /api/v1/config` reports it as 90

### Requirement: OPS-6 Querying the audit log
`GET /api/v1/audit-records` ([MGMT-5](../management/spec.md)) SHALL list records newest first, paginated, with
filters for time range, endpoint, bundle, server, tool, caller (`user_id`, `api_key_id`) and status. The admin UI SHALL
offer an audit page filtering by time range, endpoint, tool and status, with CSV export of the listed records.

#### Scenario: Filters narrow the list
- **WHEN** a client lists audit records with `endpoint_name=main&status=denied`
- **THEN** only denied records on endpoint `main` are returned

#### Scenario: CSV export
- **WHEN** an admin presses "Export CSV" on the audit page
- **THEN** a CSV of the currently listed records is downloaded

### Requirement: OPS-7 Reconciliation source
The audit log is the metering **reconciliation source** ([PROT-26](../protocol/spec.md)): for every invocation whose
pre-call hook succeeded, the gateway SHALL submit an audit record with a terminal status (`success`, `error` or
`denied`) once the invocation ends.

#### Scenario: Metered call ends in error
- **GIVEN** the pre-call hook allowed the call
- **WHEN** the upstream call fails
- **THEN** a record with status `error` is submitted for it

### Requirement: OPS-8 Logs
Every log record the process writes — structlog events and standard-library loggers such as uvicorn's alike — SHALL be
rendered as one structured line per event to the process's standard error stream, in the format chosen by
`BUNDLEMCP_LOG_FORMAT` (`json`, the default, or `text` for terminals), at the minimum level set by
`BUNDLEMCP_LOG_LEVEL`. Secrets, tokens, header values, and tool arguments MUST never be logged. No debug prints in hot
paths — enforced by ruff config (`T20`) and review.

#### Scenario: Library and application logs share the JSON format
- **GIVEN** the log format is `json` and the level `INFO`
- **WHEN** uvicorn's access logger and a structlog logger each emit a record
- **THEN** both lines are JSON objects carrying `logger`, `level`, `event` and `timestamp`

#### Scenario: Records below the level are dropped
- **GIVEN** the level is `INFO`
- **WHEN** a logger emits a `DEBUG` record
- **THEN** nothing is written for it

#### Scenario: Print statements are rejected
- **WHEN** library code contains a `print(...)` call
- **THEN** `uv run ruff check .` fails with a `T20` finding

### Requirement: OPS-10 Probes
The gateway SHALL serve `/healthz` (process live) and `/readyz` (Postgres and Valkey both reachable) —
unauthenticated, for orchestrators.

#### Scenario: Liveness
- **WHEN** an orchestrator calls `GET /healthz` without credentials
- **THEN** the response is 200 `{"status": "ok"}`

#### Scenario: Readiness with both stores up
- **GIVEN** Postgres and Valkey both answer
- **WHEN** an orchestrator calls `GET /readyz` without credentials
- **THEN** the response is 200 `{"status": "ready"}`

#### Scenario: Readiness does not depend on the identity provider
- **GIVEN** the OIDC issuer is unreachable
- **WHEN** an orchestrator calls `GET /readyz`
- **THEN** the response is still 200

#### Scenario: Live store down
- **GIVEN** Valkey cannot be reached
- **WHEN** an orchestrator calls `GET /readyz`
- **THEN** the response is not 200

## Out of scope

### Audit log

- Shipping audit data to external SIEMs (operators can read the table or poll the API).

### Observability

- Bundled Grafana dashboards / alert rules (nice-to-have docs example, not a requirement).

## Notes

### Audit log

Origin: metamcp carry-over (fork feature); prior art
`../metamcp/apps/backend/src/lib/metamcp/metamcp-middleware/audit-requests.functional.ts` and the
`mcp_request_audit_logs` table.

Not yet built: an age-based purge job reading `audit_retention_days`, bundle/server/caller filters and full-result CSV
export in the UI, an exported overflow metric, and making a lost record identifiable — see the change proposals derived
from this migration.

### Observability

Origin: new. Prometheus metrics (OPS-9), degraded-response visibility (OPS-11), tracing (OPS-12) and the overhead budget
(OPS-13) are specified but not built; the in-process counters in
`packages/bundlemcp/bundlemcp/infrastructure/inprocess/counters.py` collect a few values for a future exporter but
nothing exports them.
