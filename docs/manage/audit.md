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
| `status` | `success`, `error`, `denied`, or `input_required` when a call paused for the client's input and continues on its retry. |
| `denied_reason` | Why a `denied` call was refused: a disabled tool, or a metering decision (the hook's own `reason`, verbatim). |
| `duration_ms` | Time spent on the upstream call; `null` when the call was denied before reaching it. |
| `error_message` | Truncated failure detail. A call that could not reach its upstream — including a `per_user` server the caller has not connected — is `status: error` with `error_message: upstream_not_connected`, **not** `denied`, so a dashboard filtering on `denied` will not see it. |
| `created_at` | When the record was written. |

Tool **arguments and results are not stored**. Neither are authentication failures or rate-limit rejections; those go to
the logs, not the audit log.

Records are written asynchronously after the response, so auditing never adds
latency to a call. The queue is in-process and bounded: an overflow is logged and
counted rather than silently dropped, and an abrupt process death loses whatever
was still queued. Treat the audit log as reliable for reporting, and not as a
ledger of record for billing — see
[Reconciling with a metering hook](#reconciling-with-a-metering-hook).

## Querying

The **Audit** page filters by time range, endpoint, tool and status, and exports the loaded page as CSV. The API also
filters by bundle, upstream server and caller, with these query parameters:

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
| `offset`, `limit` | Pagination, default 50, maximum 500. |

Results are listed newest first and paginated like every other list route, with `items`, `total`, `offset` and
`limit`.

## Retention

::: warning Nothing purges the audit log yet
`audit_retention_days` (a runtime setting, default 90) is the *intended*
retention and is read by nothing today: no purge job exists, so the table grows
without bound. Plan for that — set up your own scheduled `DELETE`, or a
partition-drop, against the `audit_records` table, and size the volume for the
call rate you expect.
:::

If you meter calls and reconcile against the audit log, whatever retention you
implement must be longer than your reconciliation window. Pull records out
through the API on a schedule if you need them beyond that.

## Reconciling with a metering hook

For every call whose pre-call metering decision succeeded, an audit record with a terminal status eventually exists. A
debit with no matching record means the gateway died between the pre-call and post-call hooks, and the application layer
can refund it out of band. The details are in
[Metering hook](/integrate/metering-hook#crash-reconciliation).
