## MODIFIED Requirements

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
