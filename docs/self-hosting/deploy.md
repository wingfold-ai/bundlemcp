# Production deployment

The reference stack in `deploy/docker-compose.yml` is built for local
development. Running it for other people means putting a TLS-terminating
reverse proxy in front, replacing the dev identity provider and every inline
secret, and telling the gateway its public identity. This page walks through
the topology; [Configuration](/self-hosting/configuration) lists every
setting.

## Topology

<LikeC4Diagram view="production" />

- The **gateway** serves the MCP endpoints, the OAuth server, the login flow
  and the management API on one port. You can run several replicas behind
  the proxy; they share Postgres and Valkey and need nothing else in common.
- The **web** container is the admin UI, a static single-page app that calls
  the gateway's management API from the browser. It is optional: everything
  it does is available through the API.
- The **identity provider** is any OIDC-compliant issuer. Keycloak is what the
  dev stack ships and what the maintainers run, but nothing depends on it.

## Public URL

`BUNDLEMCP_PUBLIC_URL` is the single source of the externally visible base
URL, for example `https://gw.example.com`. The OAuth issuer, the
`.well-known` metadata, redirect URIs, consent pages and the admin session
cookie's `Domain` and `Secure` attributes all derive from it, never from the
incoming `Host` header.

Set it to exactly what clients reach. A wrong value shows up as OAuth clients
being sent to the wrong issuer, or a login cookie that never sticks.

## Reverse proxy

Terminate TLS at the proxy and forward to the gateway on port 8000 and the
web app on port 3000. Then:

1. Set `BUNDLEMCP_TRUSTED_PROXIES` to the CIDRs your proxies connect from,
   for example `["10.0.0.0/8"]`. `X-Forwarded-For` is honoured only from
   those peers; from anyone else the socket address is used. Without this,
   per-client rate limits and audit records attribute every request to the
   proxy.
2. Allow long-lived responses. Handshake-era clients hold a `GET` stream
   open on the endpoint URL for server-initiated messages, and a tool call
   can run for the configured call timeout (60 s by default, up to
   `max_total_timeout`). Set the proxy's read and idle timeouts accordingly
   and do not buffer responses.
3. Pass request bodies through unchanged. The gateway enforces its own body
   size limits.

A minimal Caddyfile:

```
gw.example.com {
    reverse_proxy gateway:8000 {
        flush_interval -1
    }
}

admin.example.com {
    reverse_proxy web:3000
}
```

## Browser origins and the web app

The web app talks to the management API with the admin session cookie, so
the gateway must allow its origin:

```
BUNDLEMCP_WEB_ORIGINS=["https://admin.example.com"]
```

Only these origins receive credentialed CORS headers, and they are also the
allow-list for the CSRF origin check on cookie-authenticated mutations.
The web container itself needs one variable:

```
NUXT_PUBLIC_API_BASE=https://gw.example.com
```

If you serve the web app under the gateway's own origin behind the proxy,
`BUNDLEMCP_WEB_ORIGINS` can stay empty: same-origin requests need no CORS.

## Identity provider

Point the gateway at your issuer's discovery document and register a
confidential client whose redirect URI is `<public url>/login/callback`:

```
BUNDLEMCP_OIDC_DISCOVERY_URL=https://idp.example.com/realms/prod/.well-known/openid-configuration
BUNDLEMCP_OIDC_CLIENT_ID=bundlemcp-gateway
BUNDLEMCP_OIDC_CLIENT_SECRET=...
BUNDLEMCP_ADMIN_EMAILS=["ops@example.com"]
```

Details and provider-specific notes are in
[Identity provider](/self-hosting/identity-provider).

## Secrets

Generate real values for every secret the dev compose file defaults inline:

| Variable | Generate with |
|---|---|
| `BUNDLEMCP_INITIAL_SERVICE_KEY` | `python -c "import secrets;print('bmcp_sk_'+secrets.token_urlsafe(32))"` |
| `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` | `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"` |
| `BUNDLEMCP_OIDC_CLIENT_SECRET` | Whatever your identity provider issued |
| Postgres password | Your platform's secret store |

The initial service key is only consulted while no service key exists, so
it is safe to rotate away afterwards: create a new service key through the
API, then delete the first one.

Token encryption keys protect stored upstream OAuth tokens. The gateway boots
without them, but a server with `auth_mode: upstream_oauth` cannot be used
until they are set. Losing every key invalidates every stored upstream
connection; users simply reconnect.

## Health checks and readiness

| Route | Meaning |
|---|---|
| `GET /healthz` | The process is alive. |
| `GET /readyz` | Postgres and Valkey are reachable and the schema is current. Returns non-200 until migrations have run. |

Both are unauthenticated. Wire `/readyz` into your orchestrator's readiness
probe and the proxy's upstream health check; the gateway image's own
`HEALTHCHECK` already polls it.

## Migrations and upgrades

The gateway image runs `alembic upgrade head` before starting the server, so
a plain image bump applies the schema change. With several replicas, start
the new version as a rolling update:

1. Migrations are written to be backward-compatible one release back, so
   old replicas keep working against the new schema during the rollout.
2. Live session records in Valkey carry a schema version. A release reads the
   previous release's records or treats them as expired, which makes the
   client re-initialise rather than fail.
3. `/readyz` stays false on a new replica until it sees the current schema,
   so the proxy does not route to it early.

Read the release notes before jumping more than one version.

## Scaling out

Run more gateway replicas behind the proxy. There is no sticky-session
requirement: handshake-era sessions live in Valkey, modern-era requests
carry everything they need. Rate limits are counted in Valkey, so they hold
across replicas.

The one exception is a **live stream**: a handshake-era client's `GET` event
stream, or a modern client's `subscriptions/listen`, is pinned to the replica
holding the connection. The signal bus in Valkey routes notifications to it.
Nothing about that requires proxy configuration, but it is why Valkey must be
one shared instance, not one per replica.

## Backups

Postgres holds **all** durable state: configuration, users, OAuth clients
and tokens, upstream tokens, the audit log. A `pg_dump` of the database is a
complete backup.

```bash
docker compose -f deploy/docker-compose.yml exec postgres \
  pg_dump -U bundlemcp bundlemcp > bundlemcp-$(date +%F).sql
```

Restore into an empty database and start the gateway; migrations bring the
schema forward if the dump is older than the running version.

Valkey is deliberately **not** backed up. It holds sessions and counters;
losing it means clients re-initialise and rate-limit windows restart.

Keep the token encryption keys and the OIDC client secret with the dump. A
restored database whose upstream tokens were encrypted with a key you no
longer have cannot use those connections.

## Network egress

The gateway makes outbound HTTP requests to server URLs, to upstream OAuth
providers, to client metadata documents and to your identity provider. All of
them go through one egress policy:

- link-local and cloud metadata ranges (`169.254.0.0/16` and the IPv6
  equivalents) and the gateway's own loopback are blocked;
- private RFC 1918 ranges are allowed, since compose and cluster networks
  are the common case;
- `BUNDLEMCP_EGRESS_ALLOW_CIDRS` widens and `BUNDLEMCP_EGRESS_DENY_CIDRS`
  narrows the policy. The allow list is evaluated first.

The policy applies to the resolved IP at connect time, including after
redirects, so DNS tricks do not bypass it. An identity provider that resolves
to loopback, as a dev Keycloak on the same host might, needs an allow entry.

## Checklist

- [ ] `BUNDLEMCP_PUBLIC_URL` is the HTTPS URL clients reach.
- [ ] `BUNDLEMCP_TRUSTED_PROXIES` names the proxy.
- [ ] Identity provider configured, redirect URI registered, admin emails set.
- [ ] Every secret replaced; `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` set if any server uses upstream OAuth.
- [ ] `BUNDLEMCP_WEB_ORIGINS` contains the admin UI origin.
- [ ] `BUNDLEMCP_BOOTSTRAP_STRICT=true` if you provision from a bootstrap file.
- [ ] `/readyz` wired into the proxy and orchestrator.
- [ ] Postgres backups scheduled and a restore rehearsed.
