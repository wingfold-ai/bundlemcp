# Audit log

Every `tools/call` through every endpoint produces one audit record in Postgres: who called what, where it went, how
long it took, how it ended. It is the answer to "what happened?", and the reconciliation source for an application layer
that meters calls.

## What is recorded

| Field | Meaning |
|---|---|
| `endpoint_name`, `bundle_name`, `server_name` | Where the call arrived and where it was routed, as named at the time. |
| `tool_name`, `presented_tool_name` | The upstream tool and the name the client used, including any override. |
| `user_id`, `api_key_id`, `auth_method` | The caller and how they authenticated. |
| `session_id` | The MCP session for handshake-era clients. |
| `status` | `success`, `error`, `denied`, or `input_required` when a call paused for the client's input and continues on its retry. |
| `denied_reason` | Why a denied call was refused: a disabled tool, a metering decision, a missing upstream connection. |
| `duration_ms` | Time spent on the upstream call; `null` when the call was denied before reaching it. |
| `error_message` | Truncated failure detail. |
| `created_at` | When the record was written. |

Tool **arguments and results are not stored**. Neither are authentication failures or rate-limit rejections; those go to
logs and metrics, not the audit log.

Records are written asynchronously after the response, so auditing never adds latency to a call. Under normal operation
they are durable; a queue overflow is logged and counted rather than silently dropped.

## Querying

The **Audit** page filters by time range, endpoint, bundle, server, tool, caller and status. The same filters are query
parameters on the API:

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

Results are ordered by creation time and paginated like every other list route, with `items`, `total`, `offset` and
`limit`.

## Retention

Records older than `audit_retention_days` (a runtime setting, default 90) are purged. If you meter calls and reconcile
against the audit log, keep retention longer than your reconciliation window. Pull records out through the API on a
schedule if you need them longer.

## Reconciling with a metering hook

For every call whose pre-call metering decision succeeded, an audit record with a terminal status eventually exists. A
debit with no matching record means the gateway died between the pre-call and post-call hooks, and the application layer
can refund it out of band. The details are in
[Metering hook](/integrate/metering-hook#crash-reconciliation).
