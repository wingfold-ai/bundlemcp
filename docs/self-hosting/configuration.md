# Configuration

The gateway is configured through environment variables prefixed
`BUNDLEMCP_`, read once at startup. A `.env` file in the working directory is
also read. List-valued settings are JSON arrays, for example
`BUNDLEMCP_ADMIN_EMAILS='["a@example.com","b@example.com"]'`.

A second, smaller set of **runtime settings** is editable while the gateway
runs, through the UI's Settings page or the `config` API, and takes effect
across all replicas without a restart.

## Environment variables

### Stores

| Variable | Default | Meaning |
|---|---|---|
| `BUNDLEMCP_DATABASE_URL` | `postgresql+asyncpg://bundlemcp:bundlemcp@localhost:5432/bundlemcp` | Async SQLAlchemy URL of the Postgres holding configuration, tokens and the audit log. |
| `BUNDLEMCP_REDIS_URL` | `redis://localhost:6379/0` | Valkey (or Redis) URL for live sessions, rate limits and cross-replica signalling. The `redis://` scheme is correct for Valkey. |

### Public identity

| Variable | Default | Meaning |
|---|---|---|
| `BUNDLEMCP_PUBLIC_URL` | `http://localhost:8000` | Externally reachable base URL. The OAuth issuer, discovery metadata, redirect URIs and cookie scope derive from it. |
| `BUNDLEMCP_TRUSTED_PROXIES` | `[]` | CIDRs of reverse proxies whose `X-Forwarded-*` headers are honoured. |

### Admin login

| Variable | Default | Meaning |
|---|---|---|
| `BUNDLEMCP_OIDC_DISCOVERY_URL` | unset | The issuer's OIDC discovery document. Admin login is disabled when unset. |
| `BUNDLEMCP_OIDC_CLIENT_ID` | unset | Client id registered with the provider. |
| `BUNDLEMCP_OIDC_CLIENT_SECRET` | unset | Client secret registered with the provider. |
| `BUNDLEMCP_ADMIN_EMAILS` | `[]` | Emails granted admin rights, re-evaluated at every login. |
| `BUNDLEMCP_WEB_ORIGINS` | `[]` | Browser origins allowed to call the management API with credentials, and the CSRF allow-list. Empty means same-origin only. |

### Security

| Variable | Default | Meaning |
|---|---|---|
| `BUNDLEMCP_EGRESS_ALLOW_CIDRS` | `[]` | CIDRs upstream servers may resolve to. Empty allows anything not denied. |
| `BUNDLEMCP_EGRESS_DENY_CIDRS` | `[]` | CIDRs upstream servers may never resolve to. Metadata ranges are blocked regardless. |
| `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` | `[]` | Fernet keys for stored upstream OAuth tokens. The first encrypts, all decrypt. Required before any server can use upstream OAuth. |
| `BUNDLEMCP_AUTH_FAILURE_LIMIT` | `20` | Failed authentication attempts from one IP before it is locked out. |
| `BUNDLEMCP_AUTH_FAILURE_WINDOW` | `300` | Seconds the failure count is retained. |

### Provisioning

| Variable | Default | Meaning |
|---|---|---|
| `BUNDLEMCP_BOOTSTRAP_FILE` | unset | Path to a YAML or JSON [bootstrap document](/self-hosting/bootstrap) applied at startup. |
| `BUNDLEMCP_BOOTSTRAP` | unset | The same document inline as JSON, applied after the file when both are set. |
| `BUNDLEMCP_BOOTSTRAP_STRICT` | `false` | Whether a failed bootstrap refuses startup. Use `true` in CI and production. |
| `BUNDLEMCP_INITIAL_SERVICE_KEY` | unset | A service API key provisioned on first boot when none exists, so the management API is reachable headlessly. Ignored once any service key exists. |

### Metering

| Variable | Default | Meaning |
|---|---|---|
| `BUNDLEMCP_METERING_HOOK` | unset | Import path `module:attribute` of a [metering hook](/integrate/metering-hook). Unset installs a no-op. |
| `BUNDLEMCP_METERING_HOOK_FAIL_OPEN` | `false` | Whether a tool call proceeds when the hook itself fails. `false` denies the call. |

### Protocol and logging

| Variable | Default | Meaning |
|---|---|---|
| `BUNDLEMCP_LEGACY_PROTOCOL_ENABLED` | `true` | Whether MCP revisions before 2026-07-28 (the `initialize` handshake and sessions) are still served. Switch off once every client speaks the stateless revisions. |
| `BUNDLEMCP_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`. |
| `BUNDLEMCP_LOG_FORMAT` | `json` | `json` for a log pipeline, `text` for a terminal. Applies to the web server's loggers too. |

Secrets, tokens, header values and tool arguments are never written to the
log at any level.

## Runtime settings

These are stored in Postgres, propagated to every replica, and editable from
**Settings** in the UI or through `GET/PUT/DELETE /api/v1/config/{key}`.
Deleting a key resets it to its default. Values are type-checked: a boolean
key rejects `1`, an integer key rejects `"3"`.

| Key | Default | Meaning |
|---|---|---|
| `call_timeout` | `60.0` | Seconds a single upstream tool call may take before the gateway gives up. |
| `reset_timeout_on_progress` | `true` | Whether an upstream progress notification restarts the call timeout. |
| `max_total_timeout` | `1800.0` | Absolute ceiling in seconds for one call, progress or not. |
| `session_lifetime` | `86400` | Idle lifetime in seconds of a handshake-era session record. `0` disables idle expiry. |
| `list_cache_ttl_ms` | `300000` | Milliseconds a modern-era client may cache a tools, prompts or resources list. |
| `server_error_attempts` | `3` | Consecutive connection failures before a server is marked `error`. |
| `audit_retention_days` | `90` | Age after which audit records are purged. |
| `authorization_code_lifetime` | `600` | Seconds a client has to redeem an authorization code from the gateway's OAuth server. |
| `access_token_lifetime` | `3600` | Seconds an access token issued by the gateway's OAuth server stays valid. |
| `refresh_token_lifetime` | `604800` | Seconds a refresh token issued by the gateway's OAuth server may be exchanged. |

```bash
curl -s -X PUT https://gw.example.com/api/v1/config/call_timeout \
  -H "Authorization: Bearer $SERVICE_KEY" -H "Content-Type: application/json" \
  -d '{"value": 120.0}'
```

## The web container

The admin UI reads one variable at runtime:

| Variable | Default | Meaning |
|---|---|---|
| `NUXT_PUBLIC_API_BASE` | `http://localhost:8000` | Origin of the gateway the browser should call. Must be reachable from the user's browser, not just from the container. |
