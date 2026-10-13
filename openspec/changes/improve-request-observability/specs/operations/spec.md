## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: OPS-12 Optional tracing
The gateway SHALL support OpenTelemetry tracing — request spans for HTTP, Postgres and Valkey, plus one span per
upstream tool call — configured through the standard `OTEL_*` environment variables. Tracing MUST be off by default and
zero-cost when off: no tracing code is loaded and no span is created. Spans MUST NOT carry secrets, header values or
tool arguments.

#### Scenario: Off by default
- **GIVEN** no OpenTelemetry exporter endpoint is configured
- **WHEN** the gateway starts and serves a tool call
- **THEN** no OpenTelemetry module is imported and no span is exported

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
