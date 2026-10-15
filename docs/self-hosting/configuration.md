# Configuration

The gateway is configured through environment variables prefixed `BUNDLEMCP_`, read once at startup. A `.env` file in
the working directory is also read. List-valued settings are JSON arrays, for example
`BUNDLEMCP_ADMIN_EMAILS='["a@example.com","b@example.com"]'`.

A second, smaller set of **runtime settings** is editable while the gateway runs, through the UI's Settings page or the
`config` API, and takes effect across all replicas without a restart.

## Environment variables

### Stores

| Variable | Default | Meaning |
|---|---|---|
| `BUNDLEMCP_DATABASE_URL` | `postgresql+asyncpg://bundlemcp:bundlemcp@localhost:5432/bundlemcp` | Async SQLAlchemy URL of the Postgres holding configuration, tokens and the audit log. The default only suits a gateway running on the same machine as Postgres: inside a container, `localhost` is the container itself, the gateway finds no database there and does not start. |
| `BUNDLEMCP_REDIS_URL` | `redis://localhost:6379/0` | Valkey (or Redis) URL for live sessions, rate limits and cross-replica signalling. The `redis://` scheme is correct for Valkey. With the default inside a container, the gateway never reports ready and requests that need live state answer `503`. |

### Public identity

| Variable | Default | Meaning |
|---|---|---|
| `BUNDLEMCP_PUBLIC_URL` | `http://localhost:8000` | Externally reachable base URL, exactly as clients reach it, e.g. `https://mcp.example.com`. The OAuth issuer, discovery metadata, redirect URIs and cookie scope derive from it. The default works only on the gateway's own machine: anyone else is sent to `localhost` to sign in, so OAuth and the admin login fail for them. |
| `BUNDLEMCP_TRUSTED_PROXIES` | `[]` | CIDRs your reverse proxies connect from, e.g. `["10.0.0.0/8"]`; their `X-Forwarded-For` is honoured (the rightmost entry that is not one of these proxies), so the gateway sees each client's real address. `X-Forwarded-Proto` and `X-Forwarded-Host` are never read; `BUNDLEMCP_PUBLIC_URL` decides every published URL. Empty: behind a proxy, every request appears to come from the proxy. Everyone then shares one failed-login counter, so a few bad credentials from one client lock out all; anonymous callers share one rate limit; and the audit log shows no real client addresses. |

### Admin login

| Variable | Default | Meaning |
|---|---|---|
| `BUNDLEMCP_OIDC_DISCOVERY_URL` | unset | Your identity provider's discovery document, `…/.well-known/openid-configuration` ([Identity provider](/self-hosting/identity-provider)). Unset, or without the client id and secret below: nobody can sign in (the login answers `503`), so no MCP client can connect through OAuth either; only API keys work. |
| `BUNDLEMCP_OIDC_CLIENT_ID` | unset | Client id you registered for the gateway at the provider. |
| `BUNDLEMCP_OIDC_CLIENT_SECRET` | unset | Client secret the provider issued for that client. It comes from the provider; you do not generate it. |
| `BUNDLEMCP_ADMIN_EMAILS` | `[]` | Emails granted admin rights, re-evaluated at every login. Empty: nobody is an administrator; everyone who signs in sees only the catalogue, and the gateway can be configured only with a service API key. |
| `BUNDLEMCP_WEB_ORIGINS` | `[]` | Addresses (scheme and host) of admin UIs served from a different address than the gateway, e.g. `["https://admin.example.com"]` for a UI there and the gateway at `https://mcp.example.com`. Browsers let such a page call the management API with the user's login only if the gateway allows its address; the list is also the CSRF allow-list. Empty means same-origin only, which is right when the UI is served from the gateway's own address or not used; a UI elsewhere then loads no data. |

### Security

| Variable | Default | Meaning |
|---|---|---|
| `BUNDLEMCP_EGRESS_ALLOW_CIDRS` | `[]` | Exceptions to the built-in egress rule. By default the gateway refuses to connect to its own loopback and to link-local / cloud-metadata ranges (`169.254.0.0/16`), so a registered server URL cannot reach cloud credentials or the gateway itself; private networks such as `10.0.0.0/8` are allowed. An entry here is checked first and wins over every other rule, so keep it as narrow as the host you mean, e.g. `["127.0.0.1/32"]`; `0.0.0.0/0` reopens the cloud-metadata range. Empty: the built-in rule alone. See [Network egress](/self-hosting/deploy#network-egress). |
| `BUNDLEMCP_EGRESS_DENY_CIDRS` | `[]` | CIDRs outbound requests may never resolve to, unless an allow entry covers them. |
| `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` | `[]` | Keys that encrypt the tokens the gateway stores for upstream servers using upstream OAuth (people or an admin signed in to the service, or a client id and secret), so it can keep calling them without a new sign-in. The first key encrypts, all of them decrypt, which is how [rotation](/self-hosting/operations#rotating-credentials) works. [Generate](#secrets-you-generate) one. Empty: such servers cannot be used (their upstream OAuth status shows `configured: false`); everything else works. Losing every key makes stored sign-ins unreadable, and people have to sign in to those services again. |
| `BUNDLEMCP_AUTH_FAILURE_LIMIT` | `20` | Failed authentication attempts from one IP before it is locked out. |
| `BUNDLEMCP_AUTH_FAILURE_WINDOW` | `300` | Seconds the failure count is retained. |

### Client registration

How OAuth clients such as claude.ai and ChatGPT may register with the gateway's own authorization server.

| Variable | Default | Meaning |
|---|---|---|
| `BUNDLEMCP_DCR_ALLOWED_REDIRECT_URIS` | `[]` | Redirect URIs clients may register, or declare in a client metadata document. Empty accepts any https URI (or http on localhost). Syntax below. |
| `BUNDLEMCP_DCR_RATE_LIMIT` | `10` | Dynamic registrations one client IP may make per window. Registrations whose redirect URIs are all allow-listed are exempt. |
| `BUNDLEMCP_DCR_RATE_WINDOW` | `3600` | Seconds in the per-IP registration window. |
| `BUNDLEMCP_DCR_MAX_UNUSED_CLIENTS` | `1000` | Registered clients that have not yet obtained a token, across all IPs. Further registrations are refused with `429` until some are used or purged after seven days unused. Applies to allow-listed registrations too. |

**Leaving the list empty is a valid choice**, and the default: every MCP client may register, as long as the address
it sends people back to after sign-in is https (or http to `localhost`, for a client running on the person's own
machine). Choose it when you do not want to restrict which apps people connect with. Floods of fake registrations are
still held back by the other two limits in this table: at most `BUNDLEMCP_DCR_RATE_LIMIT` registrations per IP address
per window, and at most `BUNDLEMCP_DCR_MAX_UNUSED_CLIENTS` clients that never obtained a token.

The list decides **which apps** may connect, not **who** may use your bundles. Whatever client a person uses, they
still have to sign in at your identity provider, approve the consent screen, and reach an endpoint that accepts OAuth.
Restricting the list to claude.ai, say, keeps people from connecting through other apps; it lets nobody in who could not
get in before.

Each entry of `BUNDLEMCP_DCR_ALLOWED_REDIRECT_URIS` is one of:

- **An exact URI**, compared character for character: `https://claude.ai/api/mcp/auth_callback`.
- **A URI whose leftmost host label is `*`**: `https://*.example.com/oauth/callback` matches
  `https://app.example.com/oauth/callback`, but not `https://example.com/oauth/callback` or
  `https://a.b.example.com/oauth/callback`. The `*` stands for exactly one DNS label; scheme, port, path and query must
  be identical. `*` is allowed nowhere else, and at least two labels must follow it.

A malformed entry stops the gateway at startup. The list only narrows the built-in rule: an http redirect URI to
anything but localhost is refused even if listed. Set it as a JSON array, for example
`BUNDLEMCP_DCR_ALLOWED_REDIRECT_URIS='["https://claude.ai/api/mcp/auth_callback"]'` for a deployment that serves
claude.ai only.

### Upstream discovery

| Variable | Default | Meaning |
|---|---|---|
| `BUNDLEMCP_DISCOVERY_REFRESH_INTERVAL` | `1800` (30 minutes) | Seconds between re-reading every server's tool list. Picks up a server that was unreachable when you registered it, and tools that changed without the upstream announcing it. One replica refreshes per interval. **Unset** means the default, every 30 minutes. **`0` turns the refresh off entirely**: no server is re-read until you call `:refresh-tools` or change its definition. Any other value is the interval itself, so keep it in minutes, not seconds: every refresh contacts every upstream server, and a value such as `1` probes all of them about once a second. 300–3600 suits most deployments. |

### Provisioning

| Variable | Default | Meaning |
|---|---|---|
| `BUNDLEMCP_BOOTSTRAP_FILE` | unset | Path, as the gateway container sees it, to a YAML or JSON [bootstrap document](/self-hosting/bootstrap) whose upstream servers, bundles and endpoints are created or updated at every start. Unset: nothing is created at start-up; you set everything up in the UI or through the management API. |
| `BUNDLEMCP_BOOTSTRAP` | unset | The same document inline as JSON, applied after the file when both are set. |
| `BUNDLEMCP_BOOTSTRAP_STRICT` | `false` | What happens when the bootstrap document has an error. `true` stops the start, so you notice at once; use it in CI and production. `false` logs the error and starts anyway, without whatever the document failed to create. |
| `BUNDLEMCP_INITIAL_SERVICE_KEY` | unset | A service API key stored at start-up when no service key exists yet, so scripts can use the management API before anyone has signed in. Ignored as long as any service key exists. [Generate](#secrets-you-generate) it; whether to replace it later is explained in [The first service key](/manage/api-keys#the-first-service-key). Unset: no key is created, and the management API is usable only after an administrator signs in and creates one on the **API keys** page. |

### Metering

| Variable | Default | Meaning |
|---|---|---|
| `BUNDLEMCP_METERING_HOOK` | unset | Import path `module:attribute` of a [metering hook](/integrate/metering-hook). Unset installs a no-op. |
| `BUNDLEMCP_METERING_HOOK_FAIL_OPEN` | `false` | Whether a tool call proceeds when the hook itself fails. `false` denies the call. |
| `BUNDLEMCP_METERING_HTTP_URL` | unset | URL of a [metering hook that runs out of process](/integrate/metering-hook#over-http), called over HTTP instead of an in-process hook. Cannot be combined with `BUNDLEMCP_METERING_HOOK`. |
| `BUNDLEMCP_METERING_HTTP_TOKEN` | unset | Bearer token sent to that hook service. Keep it in a secret; it is never logged. |
| `BUNDLEMCP_METERING_HTTP_TIMEOUT` | `2` | Seconds the hook service has to answer a pre-call before the call counts as unanswered. |

### Upstream identity

| Variable | Default | Meaning |
|---|---|---|
| `BUNDLEMCP_IDENTITY_SUBJECT` | `internal` | What [`X-MCP-User`](/integrate/upstream-identity) names a signed-in user by: `internal` for the gateway's user id, `oidc` for the identity provider's subject. API-key callers are `api_key:<id>` either way. Switching changes the key upstream servers see for every existing user. |

### Protocol and logging

| Variable | Default | Meaning |
|---|---|---|
| `BUNDLEMCP_LEGACY_PROTOCOL_ENABLED` | `true` | Whether MCP revisions before 2026-07-28 (the `initialize` handshake and sessions) are still served. Switch off once every client speaks the stateless revisions. |
| `BUNDLEMCP_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`. |
| `BUNDLEMCP_LOG_FORMAT` | `json` | `json` for a log pipeline, `text` for a terminal. Applies to the web server's loggers too. |

Secrets, tokens, header values and tool arguments are never written to the log at any level.

## Secrets you generate

Two settings are secrets you create yourself; generate each once and keep it in your platform's secret store, never in
the repository. Any machine with `openssl` can make both.

**`BUNDLEMCP_INITIAL_SERVICE_KEY`** has to start with `bmcp_sk_`, followed by a long random string:

```bash
echo "bmcp_sk_$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')"
```

**`BUNDLEMCP_TOKEN_ENCRYPTION_KEYS`** takes a list of keys, each exactly 32 random bytes in url-safe base64 (a Fernet
key):

```bash
openssl rand -base64 32 | tr '+/' '-_'
```

Put the result in a list: `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS='["<the key>"]'`.

Without `openssl`, `python3 -c "import secrets; print('bmcp_sk_' + secrets.token_urlsafe(32))"` makes a service key
with the standard library alone. For an encryption key from the `cryptography` library itself, which a host does not
usually have installed, run it inside the gateway image:

```bash
docker run --rm your-registry/bundlemcp-gateway:$SHA \
  python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
```

The other secrets are issued elsewhere: `BUNDLEMCP_OIDC_CLIENT_SECRET` by your identity provider, the Postgres password
in `BUNDLEMCP_DATABASE_URL` by whoever runs your database. How to rotate each is in
[Rotating credentials](/self-hosting/operations#rotating-credentials).

## Runtime settings

These are stored in Postgres, propagated to every replica, and editable from **Settings** in the UI or through
`GET/PUT/DELETE /api/v1/config/{key}`. Deleting a key resets it to its default. Values are type-checked: a boolean key
rejects `1`, an integer key rejects `"3"`.

| Key | Default | Meaning |
|---|---|---|
| `call_timeout` | `60.0` | Seconds a single upstream tool call may take before the gateway gives up. |
| `reset_timeout_on_progress` | `true` | Whether an upstream progress notification restarts the call timeout. |
| `max_total_timeout` | `1800.0` | Absolute ceiling in seconds for one call, progress or not. |
| `session_lifetime` | `86400` | Idle lifetime in seconds of a handshake-era session record. `0` disables idle expiry. |
| `list_cache_ttl_ms` | `300000` | Milliseconds a modern-era client may cache a tools, prompts or resources list. |
| `server_error_attempts` | `3` | Intended number of consecutive connection failures before a server is marked `error`. **Not read yet** — the threshold is fixed at 3. |
| `audit_retention_days` | `90` | Intended age after which audit records should be purged. **Advisory only — no purge job reads it yet**; see [Audit retention](/self-hosting/operations#audit-retention). |
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
