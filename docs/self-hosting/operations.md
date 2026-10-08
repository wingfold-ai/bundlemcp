# Operations

Day-two topics: what to watch, how to rotate credentials, and what the gateway does when a dependency misbehaves.

## Logs

The gateway writes structured logs to stdout, JSON by default (`BUNDLEMCP_LOG_FORMAT=text` for a terminal). Every
request line carries a request id, the endpoint, the session id and the caller once resolved. Secrets, tokens, header
values and tool arguments never appear.

Two log events deserve alerts:

- **degraded tools list**: an endpoint served `tools/list` from the cache because an upstream was unreachable. The
  server's `health_status` flips to `error` at the same time.
- **rate limiter unavailable**: Valkey could not be reached. Traffic limits fail open by default, so this is a warning,
  not an outage.

## Health

| Route | Use |
|---|---|
| `GET /healthz` | Liveness. |
| `GET /readyz` | Readiness: Postgres and Valkey reachable, migrations applied. |

Server health is visible per server in the UI and API (`health_status`, `last_error`, `protocol_version`). A server is
marked `error` after `server_error_attempts` consecutive failures and back to `ok` on the next successful connection.

## Rotating credentials

**Service API keys.** Create a new `service` key through the UI or `POST /api/v1/api-keys`, switch your automation to
it, then delete or deactivate the old one. Deactivation propagates to every replica within the cross-replica signalling
budget, not a cache TTL.

**Token encryption keys.** `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` is an ordered list. To rotate, prepend the new key and keep
the old one:

```
BUNDLEMCP_TOKEN_ENCRYPTION_KEYS=["<new>","<old>"]
```

New writes use the first key; existing rows decrypt with any key and are re-encrypted with the first key when they are
next written. Drop the old key once you are confident no row still depends on it. Dropping every key that a row was
encrypted with invalidates that upstream connection; the affected user or admin reconnects.

**OIDC client secret.** Rotate at the provider, update `BUNDLEMCP_OIDC_CLIENT_SECRET`, restart. Existing admin sessions
survive.

## Failure behaviour

| Dependency down | Effect |
|---|---|
| Postgres | The gateway cannot serve: configuration, key validation and token validation all need it. `/readyz` reports not ready. |
| Valkey | Handshake-era sessions are lost and clients re-initialise. Traffic rate limits fail open with a warning unless an endpoint set `fail_closed: true`. The auth-failure limiter also fails open. |
| An upstream server | Its tools are still listed from the cache; calls fail with a structured MCP error. Other members of the bundle are unaffected. |
| The identity provider | Existing sessions and tokens keep working until they expire; new logins and new connector authorisations fail. |
| The metering hook | Calls are denied by default. `BUNDLEMCP_METERING_HOOK_FAIL_OPEN=true` lets them through with a log line. |

## Rate limiting

Per-endpoint limits are counted in Valkey with fixed windows, so they hold across replicas. Rejections answer HTTP 429
with `Retry-After`. Only `tools/call` counts by default; `include_initialize_list: true` on an endpoint's `rate_limit`
adds `initialize` and `tools/list`.

Separately, the gateway locks out an IP after `BUNDLEMCP_AUTH_FAILURE_LIMIT` failed authentications within
`BUNDLEMCP_AUTH_FAILURE_WINDOW` seconds. The lockout is checked before the credential, so a correct key from a
locked-out address is refused too.

## Audit retention

Audit records are **not** purged. `audit_retention_days` (90 by default)
records the intent and nothing reads it yet, so the `audit_records` table grows
for the life of the deployment. Until a purge job ships, retention is yours:
schedule a `DELETE FROM audit_records WHERE created_at < now() - interval '90 days'`,
and monitor the table's size along with the rest of the database. If an
application layer reconciles billing against the audit log, keep whatever you
implement longer than its reconciliation window.

## Not part of this release

There is no Prometheus `/metrics` route, no live log stream in the UI, no
built-in MCP inspector, no audit purge job, and no JSON export or import of the
configuration; the UI's Live logs and Inspector pages are placeholders. Use the container
logs, the audit API, and a bootstrap file instead.
