# Audit log

Every `tools/call` through every endpoint produces one audit record in Postgres: who called what, where it went, how
long it took, how it ended. It is the answer to "what happened?", and the reconciliation source for an application layer
that meters calls.

## What is recorded

| Field | Meaning |
|---|---|
| `endpoint_id` | The endpoint's id, which survives a rename. |
| `endpoint_name`, `bundle_name`, `server_name` | Where the call arrived and where it was routed, as named at the time. |
| `tool_name`, `presented_tool_name` | The upstream tool and the name the client used, including any override. |
| `user_id`, `api_key_id`, `auth_method` | The caller and how they authenticated. |
| `session_id` | The MCP session for handshake-era clients. |
| `idempotency_key` | The metering idempotency key of the invocation, the one the metering hook received, the same on every leg of a paused and resumed call. `null` for a call denied before metering, such as an unknown tool or a caller not entitled to the endpoint. |
| `status` | `success`, `error`, `denied`, or `input_required` when a call paused for the client's input and continues on its retry. |
| `denied_reason` | Why a `denied` call was refused: `unknown_or_disabled_tool`, `forbidden` (a valid credential not entitled to the endpoint), or a metering decision (the hook's own `reason`, verbatim). |
| `duration_ms` | Time spent on the upstream call; `null` when the call was denied before reaching it. |
| `error_message` | Truncated failure detail. A call that could not reach its upstream — including a `per_user` server the caller has not connected — is `status: error` with `error_message: upstream_not_connected`, **not** `denied`, so a dashboard filtering on `denied` will not see it. |
| `created_at` | When the record was written. |

Tool **arguments and results are not stored**. Neither are authentication failures or rate-limit rejections; those go to
the logs and the [metrics](/self-hosting/operations#metrics), not the audit log. A `tools/call` with a *valid*
credential on an endpoint it is not entitled to is recorded as `denied` with reason `forbidden`; other requests refused
that way are not.

Records are written asynchronously after the response, so auditing never adds latency to a call. The writer batches
records, and a failed write is retried with backoff for a minute before it is given up. Every record that cannot be
written is logged with its `idempotency_key`, so a metering ledger can tell which invocation it was:

| Log event | When |
|---|---|
| `audit.queue_overflow` | The in-process queue (1000 records) was full when the record was submitted |
| `audit.write_failed` | Postgres refused the write for longer than the retry period |
| `audit.lost_on_shutdown` | The record was still queued when the 10-second shutdown drain ran out |

Overflows and given-up writes are also counted in `bundlemcp_audit_dropped_total`. A process killed outright loses its
queue without a log line; see [Reconciling with a metering hook](#reconciling-with-a-metering-hook).

## Querying

The **Audit** page filters by time range, endpoint, bundle, server, tool, caller and status, and **Export CSV**
downloads the whole filtered result, not only the loaded page. The API takes the same filters:

```bash
curl -s "https://gw.example.com/api/v1/audit-records?endpoint_name=assistant&status=error&created_from=2026-09-01T00:00:00Z&limit=100" \
  -H "Authorization: Bearer $SERVICE_KEY"
```

| Parameter | |
|---|---|
| `created_from`, `created_to` | ISO 8601 timestamps. |
| `endpoint_name`, `bundle_name`, `server_name`, `tool_name` | Exact match on the denormalised names. |
| `user_id`, `api_key_id` | Caller filters. |
| `status` | One of the four statuses. |
| `idempotency_key` | The legs of one metered invocation. |
| `offset`, `limit` | Pagination, default 50, maximum 500. |

Results are listed newest first and paginated like every other list route, with `items`, `total`, `offset` and
`limit`. `GET /api/v1/audit-records:export` takes the same filters (no pagination) and answers the whole result as CSV,
one row per record with every field above, streamed so a large export does not load into memory.

## Retention

A purge job deletes records older than `audit_retention_days` (a runtime setting, default 90). It runs every 15
minutes on one replica at a time, reads the setting on every run, so a change applies without a restart, and deletes in
chunks so no long transaction holds the table. `0` keeps everything.

If you meter calls and reconcile against the audit log, the retention must be longer than your reconciliation window.
Pull records out through the export route on a schedule if you need them beyond that.

## Reconciling with a metering hook

For every call whose pre-call metering decision succeeded, an audit record with a terminal status eventually exists. A
debit with no matching record means the gateway died between the pre-call and post-call hooks, and the application layer
can refund it out of band. The details are in
[Metering hook](/integrate/metering-hook#crash-reconciliation).
