# operations Specification

## Purpose

What operators see while the gateway runs. The append-only audit log: one record per tool call (who, what, where, how
long, how it ended), denied calls included, never arguments or results, written asynchronously without slowing calls,
queryable through the API and UI, and the reconciliation source for an application layer's billing. Structured logs and
the health and readiness probes for orchestrators. Prometheus metrics, optional tracing, and the live log view of every
replica's recent events.

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
Denied calls (disabled or unknown tool, metering deny, and a `tools/call` whose credential is valid but not entitled to
the endpoint) SHALL be audited with `status=denied` and the reason; auth failures and rate-limit rejections SHALL NOT be
audit records ([EP-18](../endpoints/spec.md)) — they go to logs and to the exported metrics
([OPS-9](../operations/spec.md)).

#### Scenario: Metering denies a call
- **WHEN** the metering hook denies a call with reason `insufficient_credits`
- **THEN** a record with status `denied` and `denied_reason` `insufficient_credits` is written

#### Scenario: Disabled tool
- **WHEN** a client calls a tool that is disabled in the bundle
- **THEN** a record with status `denied` and reason `unknown_or_disabled_tool` is written

#### Scenario: Valid credential not entitled to the endpoint
- **GIVEN** an active endpoint-kind API key scoped only to endpoint `a`
- **WHEN** it is used for a `tools/call` of `echo__say` on endpoint `b`
- **THEN** the call is refused as it is today, and a record is written with endpoint `b`, the key's `api_key_id`,
  presented tool `echo__say`, status `denied` and reason `forbidden`

#### Scenario: Forbidden non-call request is not audited
- **GIVEN** the same key
- **WHEN** it is used for `tools/list` on endpoint `b`
- **THEN** the request is refused and no audit record is written

#### Scenario: Rate-limited call
- **WHEN** a call is rejected by a rate limit
- **THEN** no audit record is written for it
- **AND** the rate-limit rejection metric increases and a log line records the rejection

#### Scenario: Authentication failure
- **WHEN** a `tools/call` carries an unknown API key
- **THEN** no audit record is written, and the auth-failure metric increases

### Requirement: OPS-3 Asynchronous, bounded writing
Writing SHALL be async/fire-and-forget relative to the client response (never adds latency, never fails a call), via a
bounded in-process queue (1000 records) flushed to Postgres, and MUST be durable under normal operation: a failed write
SHALL be retried with backoff for at least 60 seconds before it is given up, and a given-up write SHALL be logged as
`audit.write_failed` with the record's idempotency key and counted in a metric. Queue overflow SHALL be counted in a
metric and logged as `audit.queue_overflow` with the dropped record's idempotency key, not lost silently. On shutdown
the queue SHALL be drained for up to 10 seconds; every record still unwritten after that SHALL be logged as
`audit.lost_on_shutdown` with its idempotency key.

#### Scenario: Response does not wait for the write
- **WHEN** a tool call completes
- **THEN** the response is returned without waiting for the audit row to be committed

#### Scenario: Queue overflow
- **GIVEN** the audit queue holds 1000 pending records
- **WHEN** another record is submitted
- **THEN** the call is unaffected, the overflow metric increases, and a warning `audit.queue_overflow` naming the
  record's idempotency key is logged

#### Scenario: Transient database failure is retried
- **GIVEN** Postgres refuses connections for 5 seconds and then recovers
- **WHEN** a record is queued during the outage
- **THEN** the record is written after recovery and no `audit.write_failed` is logged

#### Scenario: Persistent failure is visible
- **GIVEN** Postgres stays unreachable for longer than the retry period
- **WHEN** a record is queued
- **THEN** `audit.write_failed` is logged with its idempotency key and the failed-write metric increases

#### Scenario: Shutdown drains the queue
- **GIVEN** 50 records queued and Postgres reachable
- **WHEN** the gateway receives a shutdown signal
- **THEN** all 50 records are committed before the process exits

#### Scenario: Records left at the drain deadline are named
- **GIVEN** records queued and Postgres unreachable
- **WHEN** the gateway shuts down and the drain period expires
- **THEN** each unwritten record is logged as `audit.lost_on_shutdown` with its idempotency key

### Requirement: OPS-4 No arguments or results
Tool call **arguments and results SHALL NOT be stored** (privacy + size).

#### Scenario: Arguments are not persisted
- **WHEN** a client calls a tool with arguments `{"text": "secret"}`
- **THEN** the audit record contains neither the arguments nor the result

### Requirement: OPS-5 Retention setting
The runtime configuration (`Config`) SHALL carry the key `audit_retention_days`, default 90. A purge job SHALL delete
audit records older than that many days at least once per hour, run by one replica per interval, reading the current
value on every run; `0` SHALL disable purging.

#### Scenario: Default retention value
- **WHEN** no override is stored for `audit_retention_days`
- **THEN** `GET /api/v1/config` reports it as 90

#### Scenario: Old records are purged
- **GIVEN** `audit_retention_days` is 30 and records aged 10 and 40 days exist
- **WHEN** the purge job runs
- **THEN** the 40-day-old record is deleted and the 10-day-old record remains

#### Scenario: Retention changed at runtime
- **GIVEN** the purge job is running with `audit_retention_days` 90
- **WHEN** an admin sets it to 7 through the config API
- **THEN** the next run deletes records older than 7 days, without a restart

#### Scenario: Zero keeps everything
- **GIVEN** `audit_retention_days` is 0
- **WHEN** the purge job runs
- **THEN** no record is deleted

#### Scenario: One replica purges per interval
- **GIVEN** two replicas
- **WHEN** the purge interval elapses
- **THEN** exactly one of them runs the delete

### Requirement: OPS-6 Querying the audit log
`GET /api/v1/audit-records` ([MGMT-5](../management/spec.md)) SHALL list records newest first,
paginated, with filters for time range, endpoint, bundle, server, tool, caller (`user_id`, `api_key_id`), status and
idempotency key. `GET /api/v1/audit-records:export` SHALL return the whole filtered result as CSV, with the same
filters, including caller columns. The admin UI SHALL offer an audit page filtering by time range, endpoint, bundle,
server, tool, caller and status, whose CSV export downloads the whole filtered result.

#### Scenario: Filters narrow the list
- **WHEN** a client lists audit records with `endpoint_name=main&status=denied`
- **THEN** only denied records on endpoint `main` are returned

#### Scenario: UI filters by bundle, server and caller
- **WHEN** an admin filters the audit page by bundle `b`, server `echo` and an API key
- **THEN** the table lists only records matching all three

#### Scenario: CSV export
- **GIVEN** 1200 records match the current filters while the page shows the first 100
- **WHEN** an admin presses "Export CSV" on the audit page
- **THEN** a CSV with a header and 1200 rows is downloaded, carrying `user_id`, `api_key_id`, `auth_method` and
  `idempotency_key` columns

#### Scenario: Export route applies the list's filters
- **WHEN** a client calls `GET /api/v1/audit-records:export?status=error` with a service key
- **THEN** the response is `text/csv` and contains exactly the records the list route returns for `status=error`

### Requirement: OPS-7 Reconciliation source
The audit log is the metering **reconciliation source** ([PROT-26](../protocol/spec.md)): for every
invocation whose pre-call hook succeeded, the gateway SHALL submit an audit record with a terminal status (`success`,
`error` or `denied`) once the invocation ends, carrying the invocation's metering idempotency key. An invocation whose
record cannot be written SHALL be identifiable as lost: every overflow, given-up write and shutdown loss is logged with
that key.

#### Scenario: Metered call ends in error
- **GIVEN** the pre-call hook allowed the call
- **WHEN** the upstream call fails
- **THEN** a record with status `error` is submitted for it

#### Scenario: Record carries the idempotency key
- **GIVEN** the pre-call hook received idempotency key `K` for an invocation
- **WHEN** the invocation completes
- **THEN** its terminal audit record has `idempotency_key` `K`, and listing with `idempotency_key=K` returns it

#### Scenario: Lost record is identifiable
- **GIVEN** the pre-call hook received key `K` and the audit queue is full when the invocation ends
- **WHEN** the record is dropped
- **THEN** the `audit.queue_overflow` log line carries `K`

#### Scenario: Unmetered denial has no key
- **WHEN** a call is denied as an unknown tool before any pre-call hook runs
- **THEN** its record has no idempotency key

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

### Requirement: OPS-18 Management events in the audit log
The audit log SHALL also hold records of management actions that need a durable trace, distinguished by a `kind`:
`tool_call` for the records of OPS-1 and `management` for these. A management record carries an `action` naming what
happened, the acting user or API key, the time and status `success`; it has no endpoint, bundle or tool, and never a
secret value. A secret-bearing export ([SEC-11](../security/spec.md)) writes one with action
`export.secrets_included`. `GET /api/v1/audit-records` filters by `kind`, and the CSV export carries `kind` and
`action`.

#### Scenario: A secret-bearing export is recorded
- **WHEN** an admin exports with `include_secrets=true`
- **THEN** one audit record of kind `management` with action `export.secrets_included`, the admin's user id and the
  time exists, and it holds no secret value

#### Scenario: Tool-call records are unchanged
- **WHEN** a client calls a tool
- **THEN** its audit record has kind `tool_call` and no action, as before

#### Scenario: Filtering by kind
- **GIVEN** tool-call records and one management record
- **WHEN** `GET /api/v1/audit-records?kind=management` is called
- **THEN** only the management record is listed

### Requirement: OPS-14 Capped cross-replica log buffer
Gateway log events (the structured events of [OPS-8](../operations/spec.md) at or above a
configurable level threshold, plus connection and session lifecycle events) SHALL be published to a capped stream in
the RESP store (approximately the newest 10,000 entries), shared by all replicas. Publishing MUST NOT block or fail the
request that logged the event.

#### Scenario: Events from two replicas land in one buffer
- **GIVEN** two gateway replicas sharing one RESP store
- **WHEN** each replica logs an event at or above the threshold
- **THEN** both events are in the buffer, each tagged with the replica that wrote it

#### Scenario: Events below the threshold are not published
- **GIVEN** the live-log threshold is `WARNING`
- **WHEN** the gateway logs an `INFO` event
- **THEN** the event is written to the process log but not to the buffer

#### Scenario: The buffer stays capped
- **WHEN** more than 10,000 events are published
- **THEN** the buffer holds approximately the newest 10,000 and the oldest are dropped

#### Scenario: A store outage does not fail requests
- **GIVEN** the RESP store is unreachable
- **WHEN** a request logs an event
- **THEN** the request completes as usual and the event is only written to the process log

### Requirement: OPS-15 Live log page
The admin UI SHALL show a page that streams new buffer entries from the management API (a server-push stream,
admin-authenticated) with pause and resume, a level filter, and free-text, upstream and endpoint filters. Resuming
after a pause or a dropped connection continues from the last entry shown, as long as it is still in the buffer.

#### Scenario: New entries appear without reload
- **GIVEN** an admin has the live log page open
- **WHEN** the gateway logs an event at or above the threshold
- **THEN** it appears on the page within a few seconds, without a reload

#### Scenario: Filters narrow the stream
- **WHEN** the admin filters by endpoint `b1-api` and level `ERROR`
- **THEN** only entries for that endpoint at `ERROR` or above are shown

#### Scenario: Resume continues where the page paused
- **GIVEN** the admin paused the stream and three events were logged since
- **WHEN** the admin resumes
- **THEN** the three events are shown in order, without duplicates

#### Scenario: Non-admins are refused
- **WHEN** the log stream is requested without an admin session or service API key
- **THEN** the request is refused as unauthenticated

### Requirement: OPS-16 The buffer is ephemeral
The buffer SHALL be best-effort and ephemeral: losing the RESP store's data clears it, which is acceptable by design.
Durable history is the audit log and the process logs collected by the container platform.

#### Scenario: Store loss empties the view
- **WHEN** the RESP store is restarted without persistence
- **THEN** the live log page shows only events logged after the restart, and the gateway keeps serving

### Requirement: OPS-17 Same redaction as process logs
The buffer MUST carry the already-redacted events of [OPS-8](../operations/spec.md), never raw
headers, tokens, secrets or tool arguments; whatever the process log may not contain, the buffer may not contain.

#### Scenario: A credential never reaches the buffer
- **WHEN** a request carrying an API key and an `Authorization` header is served and logged
- **THEN** no buffer entry contains the key, the header value, or the tool arguments

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
