# Operations

Day-two topics: what to watch, how to rotate credentials, and what the gateway does when a dependency misbehaves.

## Logs

The gateway writes structured logs to standard error, one line per event, JSON by default
(`BUNDLEMCP_LOG_FORMAT=text` for a terminal). Every line written while serving a request carries these fields once
they are known; secrets, tokens, header values and tool arguments never appear.

| Field | What it is |
|---|---|
| `request_id` | One per HTTP request, also returned to the client as the `X-Request-Id` response header |
| `client_ip` | The client's address as the trusted-proxy policy derives it (`BUNDLEMCP_TRUSTED_PROXIES`), not the proxy's |
| `endpoint` | The endpoint the request is for |
| `session_id` | The MCP session the request names (handshake-era clients) |
| `auth_method`, `user_id`, `api_key_id` | Who is calling: the user for OAuth, the key's id (never the key) otherwise |
| `server`, `tool` | The upstream server and tool name of a `tools/call` |

Each request ends with one `http.request` line (method, path template, status, `duration_ms`); uvicorn's own access
line is not written, because its client address is the proxy's.

Two log events deserve alerts:

- **degraded tools list**: an endpoint served `tools/list` from the cache because an upstream was unreachable. The
  server's `health_status` flips to `error` at the same time.
- **rate limiter unavailable**: Valkey could not be reached. Traffic limits fail open by default, so this is a warning,
  not an outage.

### Traces

With tracing configured ([Tracing](configuration.md#tracing)), each HTTP request is a span, with child spans for its
database statements (placeholders, never values), its Valkey commands (arguments masked) and each upstream tool call
(`mcp.upstream_call`, with `bundlemcp.endpoint`, `bundlemcp.server`, `bundlemcp.tool` and `bundlemcp.status`). The OAuth
and login routes are not traced, because their query strings carry codes and state. No span carries a key, a header
value or tool arguments.

## Health

| Route | Use |
|---|---|
| `GET /healthz` | Liveness. |
| `GET /readyz` | Readiness: Postgres and Valkey reachable, migrations applied. |

Server health is visible per server in the UI and API (`health_status`, `last_error`, `protocol_version`). A server is
marked `error` after `server_error_attempts` (default 3) consecutive connection failures, counted across discovery,
the periodic refresh and live tool calls on every replica, and back to `ok` on the next answer. The count lives in
Valkey (`bmcp:health:streak:*`, expiring after a day without failures); while Valkey is unreachable nothing is
counted and calls are unaffected.

## Rotating credentials

**Service API keys.** Create a new `service` key through the UI or `POST /api/v1/api-keys`, switch your automation to
it, then delete or deactivate the old one. Deactivation propagates to every replica within the cross-replica signalling
budget, not a cache TTL.

**Token encryption keys.** `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` is an ordered list: the first key encrypts, all of them
decrypt. The gateway encrypts two kinds of stored value with it, upstream OAuth tokens and upstream OAuth client
secrets. To rotate:

1. Prepend the new key, keep the old one, and restart every replica:

   ```
   BUNDLEMCP_TOKEN_ENCRYPTION_KEYS=["<new>","<old>"]
   ```

2. Wait. New writes use the new key, and a value still under the old key is re-encrypted the next time it is read.
   Values nobody reads are moved by a background pass that one replica runs every
   `BUNDLEMCP_TOKEN_REENCRYPTION_INTERVAL` seconds (an hour by default). Each pass logs `token_encryption.swept` with
   `rewritten`, `remaining_on_old_key` and `undecryptable`.
3. Once a pass reports `remaining_on_old_key=0`, nothing stored needs the old key. Wait one more `max_total_timeout`
   (30 minutes by default) as well: a tool call waiting on client input carries a state sealed with the key, and it
   would have to start over.
4. Remove the old key and restart.

`undecryptable` counts values that no configured key reads, for example because a key was dropped too early; they are
left as they are. Each one is an upstream connection whose user or admin has to connect again.

**OIDC client secret.** Rotate at the provider, update `BUNDLEMCP_OIDC_CLIENT_SECRET`, restart. Existing admin sessions
survive.

## Failure behaviour

| Dependency down | Effect |
|---|---|
| Postgres | Every request that needs a credential checked or configuration read answers `503` with `Retry-After` (a JSON-RPC error on MCP endpoints): a valid key is never refused with `401`, and nothing answers `500`. Configuration changes answer `503` too. Nothing is served from a stale copy; requests work again without a restart once it is back. `/readyz` reports not ready. |
| Valkey | Requests that need a session answer `503` with `Retry-After` while it is unreachable. The gateway reconnects on its own once Valkey is back; handshake-era sessions the restart lost answer `404` and clients re-initialise. Traffic rate limits fail open with a warning unless an endpoint set `fail_closed: true`. The auth-failure limiter also fails open. |
| An upstream server | Its tools are still listed from the cache; calls fail with a structured MCP error. Other members of the bundle are unaffected. |
| The identity provider | Existing sessions and tokens keep working until they expire; new logins and new connector authorisations answer `503` with `Retry-After`, and work again without a restart once it is back. |
| The metering hook | Calls are denied by default. `BUNDLEMCP_METERING_HOOK_FAIL_OPEN=true` lets them through with a log line. |

## Rate limiting

Per-endpoint limits are counted in Valkey with fixed windows, so they hold across replicas. Rejections answer HTTP 429
with `Retry-After`. Only `tools/call` counts by default; `include_initialize_list: true` on an endpoint's `rate_limit`
adds `initialize` and `tools/list`.

Separately, the gateway locks out an IP after `BUNDLEMCP_AUTH_FAILURE_LIMIT` failed authentications within
`BUNDLEMCP_AUTH_FAILURE_WINDOW` seconds. The lockout is checked before the credential, so a correct key from a
locked-out address is refused too.

Dynamic client registration at `POST /oauth/register` has its own per-IP limit and a cap on registered clients that
never obtained a token. A hosted client such as claude.ai registers from its own servers, so all of its users share one
IP's budget; listing its callback in the allow-list exempts it from the per-IP limit. The variables and their defaults
are under [Client registration](/self-hosting/configuration#client-registration).

## Audit retention

Audit records older than `audit_retention_days` (90 by default, `0` keeps everything) are deleted by a purge job that
runs every 15 minutes on one replica at a time and logs `audit.purged` with the count. A change to the setting applies
at the next run. If an application layer reconciles billing against the audit log, keep the retention longer than its
reconciliation window; see [Audit log](/manage/audit#retention).

## Not part of this release

There is no Prometheus `/metrics` route, no live log stream in the UI, no
built-in MCP inspector, and no JSON export or import of the
configuration; the UI's Live logs and Inspector pages are placeholders. Use the container
logs, the audit API, and a bootstrap file instead.
