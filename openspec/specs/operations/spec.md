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
`BUNDLEMCP_LOG_LEVEL`. Every line written while serving a request SHALL carry the request id, the client IP, and — once
resolved — the endpoint, the MCP session id and the caller (user id or API key id). Secrets, tokens, header values, and
tool arguments MUST never be logged. No debug prints in hot paths — enforced by ruff config (`T20`) and review.

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

#### Scenario: Request context on every line of a tool call
- **GIVEN** a client authenticated with API key `k1` calling a tool on endpoint `main` in session `s1`
- **WHEN** the call writes log lines (for example an upstream failure)
- **THEN** every one of those lines carries the same `request_id`, `endpoint` `main`, `session_id` `s1`, `api_key_id`
  of `k1` and `client_ip`
- **AND** none carries the key value

#### Scenario: Request id is returned to the client
- **WHEN** any HTTP request is served
- **THEN** the response carries an `X-Request-Id` header equal to the `request_id` on that request's log lines

#### Scenario: Context does not leak between requests
- **WHEN** two requests for different endpoints are served concurrently
- **THEN** each request's log lines carry only its own request id, endpoint and caller

#### Scenario: Unresolved fields are omitted
- **WHEN** a request is rejected before its credential is evaluated
- **THEN** its log lines carry `request_id` and `client_ip` but no caller field

### Requirement: OPS-10 Probes
The gateway SHALL serve `/healthz` (process live) and `/readyz` (Postgres and Valkey both reachable, and the database
schema at or past the migration head this release ships with) — unauthenticated, for orchestrators. When `/readyz` is
not ready for any of these reasons it SHALL answer 503 with a body naming the failing check, never an unhandled 500.

#### Scenario: Liveness
- **WHEN** an orchestrator calls `GET /healthz` without credentials
- **THEN** the response is 200 `{"status": "ok"}`

#### Scenario: Readiness with both stores up
- **GIVEN** Postgres and Valkey both answer and the schema is at the head this release ships with
- **WHEN** an orchestrator calls `GET /readyz` without credentials
- **THEN** the response is 200 `{"status": "ready"}`

#### Scenario: Readiness does not depend on the identity provider
- **GIVEN** the OIDC issuer is unreachable
- **WHEN** an orchestrator calls `GET /readyz`
- **THEN** the response is still 200

#### Scenario: Live store down
- **GIVEN** Valkey cannot be reached
- **WHEN** an orchestrator calls `GET /readyz`
- **THEN** the response is 503 and names `valkey` as the failing check

#### Scenario: Postgres down
- **GIVEN** Postgres cannot be reached
- **WHEN** an orchestrator calls `GET /readyz`
- **THEN** the response is 503 and names `postgres` as the failing check

#### Scenario: Schema behind the code
- **GIVEN** the database's applied migration is older than the head this release ships
- **WHEN** an orchestrator calls `GET /readyz`
- **THEN** the response is 503 and names `migrations` as the failing check

### Requirement: OPS-12 Optional tracing
The gateway SHALL support OpenTelemetry tracing — request spans for HTTP, Postgres and Valkey, plus one span per
upstream tool call — configured through the standard `OTEL_*` environment variables. Tracing MUST be off by default and
zero-cost when off: none of the gateway's tracing code, instrumentation or exporter is loaded and no span is created.
(The MCP library depends on the OpenTelemetry API and imports it regardless; that alone records nothing.) Spans MUST
NOT carry secrets, header values or tool arguments.

#### Scenario: Off by default
- **GIVEN** no OpenTelemetry exporter endpoint is configured
- **WHEN** the gateway starts and serves a tool call
- **THEN** none of the gateway's tracing code, no instrumentation and no exporter is loaded, and no span is exported

#### Scenario: Enabled through standard variables
- **GIVEN** `OTEL_EXPORTER_OTLP_ENDPOINT` points at a collector and the tracing extra is installed
- **WHEN** a client calls `echo__say` on endpoint `main`
- **THEN** the collector receives a trace with the HTTP request span and a child span for the upstream call carrying
  endpoint `main`, server `echo`, tool `say` and the call status

#### Scenario: Spans carry no secrets
- **WHEN** a traced call is made with an API key and a forwarded identity header
- **THEN** no exported span attribute contains the key value, the header value or the tool arguments

#### Scenario: Configured but not installed
- **GIVEN** `OTEL_EXPORTER_OTLP_ENDPOINT` is set but the tracing extra is not installed
- **WHEN** the gateway starts
- **THEN** it starts without tracing and logs one WARN saying the tracing extra is missing

### Requirement: OPS-13 Overhead budget report
The integration suite SHALL measure the latency the gateway adds to a `tools/call` (gateway path versus a direct call
to the same upstream) and report the p95 difference against a budget of 50 ms. The report MUST be visible in the CI run;
exceeding the budget SHALL NOT fail the run.

#### Scenario: Overhead is reported
- **WHEN** the integration suite runs against the compose stack
- **THEN** it prints the direct and gateway p50/p95 latencies, the p95 overhead and whether the 50 ms budget is met,
  and stores the same figures as a CI artifact

#### Scenario: Over budget is not a failure
- **GIVEN** a run whose measured p95 overhead is above 50 ms
- **WHEN** the suite finishes
- **THEN** the report marks the budget as exceeded and the job's outcome is decided by the other tests only

### Requirement: OPS-9 Prometheus metrics
The gateway SHALL serve Prometheus text-format metrics at `/metrics`, authenticated like the management API (a service
API key or an admin session), exposing at
minimum: tool-call count and duration histogram (labels endpoint, server, status), active sessions, upstream in-flight
calls and failures per server, rate-limit rejections, metering denies, audit queue depth, and Postgres and Valkey
health. Each replica SHALL export its own values; operators scrape every replica.

#### Scenario: Tool call is counted and timed
- **GIVEN** a successful `tools/call` of `echo__say` on endpoint `main`
- **WHEN** `/metrics` is scraped with a service API key
- **THEN** the tool-call counter with labels `endpoint="main"`, `server="echo"`, `status="success"` has increased by
  one and the duration histogram has one more observation under the same labels

#### Scenario: Metrics require a service key
- **WHEN** `/metrics` is requested without credentials
- **THEN** the response is 401 and carries no metric values

#### Scenario: Endpoint keys cannot read metrics
- **WHEN** `/metrics` is requested with an endpoint-kind API key
- **THEN** the response is 403 and carries no metric values

#### Scenario: Store health is exported
- **GIVEN** Valkey cannot be reached
- **WHEN** `/metrics` is scraped
- **THEN** the store-health gauge for `valkey` reads 0 and the one for `postgres` reads 1

#### Scenario: Each replica exports its own counters
- **GIVEN** two replicas behind one load balancer
- **WHEN** a tool call is served by replica A only
- **THEN** replica A's tool-call counter increases and replica B's does not, so summing the scrapes of both counts the
  call exactly once

#### Scenario: Metering denies are counted
- **WHEN** the metering hook denies a call on endpoint `main`
- **THEN** the metering-deny counter for `endpoint="main"` increases by one

#### Scenario: Metrics can be switched off
- **GIVEN** `BUNDLEMCP_METRICS_ENABLED=false`
- **WHEN** `/metrics` is requested
- **THEN** the response is 404

### Requirement: OPS-11 Degraded-response visibility
When an endpoint serves a `tools/list` that includes a member upstream whose health is `error`, so the listed tools are
the last-known cache rather than a fresh view, the gateway MUST increment a dedicated degraded-response metric
(labels endpoint, server) and write a WARN log naming the endpoint and the server — never silently.

#### Scenario: Unhealthy member makes the listing degraded
- **GIVEN** bundle `b` with members `echo` (health `ok`) and `weather` (health `error`), exposed on endpoint `main`
- **WHEN** a client calls `tools/list` on `main`
- **THEN** the response still lists the cached tools of both members
- **AND** the degraded-`tools/list` counter for `endpoint="main"`, `server="weather"` increases by one
- **AND** a WARN log record names endpoint `main` and server `weather`

#### Scenario: Healthy listing is not degraded
- **GIVEN** every member of the bundle has health `ok`
- **WHEN** a client calls `tools/list`
- **THEN** the degraded-`tools/list` counter does not change and no WARN is written

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
