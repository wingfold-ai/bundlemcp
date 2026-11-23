---
description: "Deploy the self-hosted bundlemcp MCP gateway to production: a TLS reverse proxy, your own identity
  provider, real secrets and the public URL."
---

# Production deployment

The reference stack in `deploy/docker-compose.yml` is built for local development. Running it for other people means
putting a TLS-terminating reverse proxy in front, replacing the dev identity provider and every inline secret, and
telling the gateway its public identity. This page walks through the topology;
[Configuration](/self-hosting/configuration) lists every setting.

## Get the images

<RepositoryNotice />

Every push to `main` publishes both images to the GitHub Container Registry, tagged `:latest` and with the full commit
SHA. Every release publishes them under its version as well:

```text
ghcr.io/wingfold-ai/bundlemcp-gateway:1.2.0     # a release
ghcr.io/wingfold-ai/bundlemcp-web:1.2.0
ghcr.io/wingfold-ai/bundlemcp-gateway:<sha>     # any commit on main
```

Pin a release version, or a SHA or digest, rather than `:latest`, which moves with every merge to `main`. Every merge
that adds or fixes something is a release, versioned from its pull request's title. A release's notes on GitHub come
from [`CHANGELOG.md`](https://github.com/wingfold-ai/bundlemcp/blob/main/CHANGELOG.md) and name the
[metering-hook protocol version](/integrate/metering-hook#versioning) it ships; read them before upgrading. To build
from a checkout instead, for your own registry:

```bash
git clone https://github.com/wingfold-ai/bundlemcp.git && cd bundlemcp
SHA=$(git rev-parse --short HEAD)

docker build -f apps/gateway/Dockerfile -t your-registry/bundlemcp-gateway:$SHA .
docker build -f apps/web/Dockerfile     -t your-registry/bundlemcp-web:$SHA .

docker push your-registry/bundlemcp-gateway:$SHA
docker push your-registry/bundlemcp-web:$SHA
```

### Verify an image

Images published after v0.4.0 carry an SBOM and a signed SLSA build provenance record, so you can check that an image
was built by this repository's release workflow from the commit it names before you deploy it:

```bash
gh attestation verify oci://ghcr.io/wingfold-ai/bundlemcp-gateway:<version> --owner wingfold-ai
docker buildx imagetools inspect ghcr.io/wingfold-ai/bundlemcp-gateway:<version> --format '{{ json .SBOM }}'
```

The first command fails for an image that was not built by the workflow, or was changed after it was pushed.

"Upgrading" means deploying a newer release: read every changelog entry between the two versions first — see
[Migrations and upgrades](#migrations-and-upgrades) for what to look for in them. A merge that releases nothing
(documentation, tests, CI) still publishes `:latest` and `:<sha>`.

## Topology

<LikeC4Diagram view="production" />

- The **gateway** serves the MCP endpoints, the OAuth server, the login flow and the management API on one port. You can
  run several replicas behind the proxy; they share Postgres and Valkey and need nothing else in common.
- The **web** container is the admin UI, a static single-page app that calls the gateway's management API from the
  browser. It is optional: everything it does is available through the API.
- The **identity provider** is any OIDC-compliant issuer. Keycloak is what the dev stack ships and what the maintainers
  run, but nothing depends on it.

## Public URL

[`BUNDLEMCP_PUBLIC_URL`](/self-hosting/configuration#public-identity) is the single source of the externally visible
base URL, for example `https://gw.example.com`.
The OAuth issuer, the `.well-known` metadata, redirect URIs and consent pages all derive from it, never from the
incoming `Host` header. The admin session cookie is host-only (it sets no `Domain`), and its `Secure` attribute follows
the public URL's scheme: set when the URL is `https`.

Set it to exactly what clients reach. A wrong value shows up as OAuth clients being sent to the wrong issuer, or a login
cookie that never sticks.

## Reverse proxy

Terminate TLS at the proxy and forward to the gateway on port 8000 and the
web app on port 3000. Then:

1. Set `BUNDLEMCP_TRUSTED_PROXIES` to the CIDRs your proxies connect from,
   for example `["10.0.0.0/8"]`. `X-Forwarded-For` is honoured only from
   those peers; from anyone else the socket address is used. Without this,
   per-client rate limits and audit records attribute every request to the
   proxy. Each proxy must **append** the address it saw to `X-Forwarded-For`
   (nginx's `$proxy_add_x_forwarded_for`, and the default in Traefik and
   Caddy). The gateway reads the list from the right and takes the first entry
   that is not one of your proxies, so whatever a client writes into the header
   itself is ignored. List every proxy in the chain, a CDN included; an
   unlisted one becomes the client address. `X-Forwarded-Proto` and
   `X-Forwarded-Host` are not read: every URL the gateway publishes comes from
   `BUNDLEMCP_PUBLIC_URL`.
2. Allow long-lived responses and do not buffer them. Session-era clients hold
   a `GET` stream open for server-initiated messages, and a tool call can run
   for `call_timeout` (60 s by default) up to a `max_total_timeout` ceiling of
   1800 s. Set the proxy's read and idle timeouts at or above the ceiling you
   allow.
3. Allow a request body of at least 4 MiB — the cap the gateway enforces
   itself on `/{endpoint}/mcp` and `/api/v1`, answering `413` above it, also
   for a chunked body. A proxy limit below that turns a request the gateway
   would have accepted into the proxy's own error. If you raise
   `max_request_bytes`, raise the proxy's limit with it.

These three numbers — **1800 s**, **4 MiB**, **no buffering** — are the whole
of it. Two of them are below nginx's defaults; Traefik's defaults only miss the
timeout.

::: code-group

```txt [Caddy]
gw.example.com {
    reverse_proxy gateway:8000 {
        flush_interval -1          # stream SSE straight through
    }
}

admin.example.com {
    reverse_proxy web:3000
}
```

```nginx [nginx]
# nginx defaults break both long calls and large bodies, so set all three.
location / {
    proxy_pass http://gateway:8000;
    proxy_http_version 1.1;
    proxy_buffering off;           # SSE streams; default is on
    proxy_read_timeout 1800s;      # >= max_total_timeout; default is 60s
    client_max_body_size 8m;       # the gateway rejects >4 MiB itself; default is 1m
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;   # appends
}
```

```yaml [Traefik]
# Traefik v3 with Docker labels. It streams responses and does not cap request
# bodies by default; only its 60 s request read timeout needs raising.
services:
  traefik:
    image: traefik:v3.5
    command:
      - --providers.docker=true
      - --providers.docker.exposedbydefault=false
      - --entrypoints.websecure.address=:443
      # >= max_total_timeout; the default 60s cuts long-lived streams
      - --entrypoints.websecure.transport.respondingtimeouts.readtimeout=1800s
      - --certificatesresolvers.le.acme.tlschallenge=true
      - --certificatesresolvers.le.acme.email=you@example.com
      - --certificatesresolvers.le.acme.storage=/letsencrypt/acme.json
    ports: ["443:443"]
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./letsencrypt:/letsencrypt

  gateway:
    environment:
      # the network Traefik reaches the gateway from
      BUNDLEMCP_TRUSTED_PROXIES: '["172.16.0.0/12"]'
    labels:
      - traefik.enable=true
      - traefik.http.routers.gateway.rule=Host(`gw.example.com`)
      - traefik.http.routers.gateway.entrypoints=websecure
      - traefik.http.routers.gateway.tls.certresolver=le
      - traefik.http.services.gateway.loadbalancer.server.port=8000

  web:
    labels:
      - traefik.enable=true
      - traefik.http.routers.web.rule=Host(`admin.example.com`)
      - traefik.http.routers.web.entrypoints=websecure
      - traefik.http.routers.web.tls.certresolver=le
      - traefik.http.services.web.loadbalancer.server.port=3000
```

:::

## Browser origins and the web app

The web app talks to the management API with the admin session cookie, so the gateway must allow its origin:

```
BUNDLEMCP_WEB_ORIGINS=["https://admin.example.com"]
```

What the setting does is in [Configuration](/self-hosting/configuration#admin-login). The web container itself needs
one variable:

```
NUXT_PUBLIC_API_BASE=https://gw.example.com
```

If you serve the web app under the gateway's own origin behind the proxy, `BUNDLEMCP_WEB_ORIGINS` can stay empty:
same-origin requests need no CORS.

## Identity provider

Point the gateway at your issuer's discovery document and register a confidential client whose redirect URI is
`<public url>/login/callback`:

```
BUNDLEMCP_OIDC_DISCOVERY_URL=https://idp.example.com/realms/prod/.well-known/openid-configuration
BUNDLEMCP_OIDC_CLIENT_ID=bundlemcp-gateway
BUNDLEMCP_OIDC_CLIENT_SECRET=...
BUNDLEMCP_ADMIN_EMAILS=["ops@example.com"]
```

Details and provider-specific notes are in
[Identity provider](/self-hosting/identity-provider).

## Secrets

The dev compose file sets every secret inline, with values anyone can read in the repository. Replace each one before
going live, and keep the new values in your platform's secret store:

- `BUNDLEMCP_INITIAL_SERVICE_KEY` and `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` you generate yourself, as described under
  [Secrets you generate](/self-hosting/configuration#secrets-you-generate).
- `BUNDLEMCP_OIDC_CLIENT_SECRET` comes from your identity provider.
- The Postgres password, inside `BUNDLEMCP_DATABASE_URL`, comes from whoever runs your database.

What each one protects, and what happens without it, is in the [Configuration](/self-hosting/configuration) reference;
rotating them is in [Rotating credentials](/self-hosting/operations#rotating-credentials).

## Health checks and readiness

| Route | Meaning |
|---|---|
| `GET /healthz` | The process is alive. |
| `GET /readyz` | Postgres answers, Valkey answers, the database schema is at or past the migration head this image ships, and the replica is not shutting down. |

Both are unauthenticated. Wire `/readyz` into your orchestrator's readiness probe and the proxy's upstream health check;
the gateway image's own `HEALTHCHECK` already polls it.

Not ready is always `503`, never `500`, with a body naming the checks that failed:

```json
{"status": "not ready", "failing": ["migrations"],
 "checks": {"postgres": {"ok": true}, "valkey": {"ok": true},
            "migrations": {"ok": false, "reason": "schema at 0010_..., this release needs 0011_..."}}}
```

A schema written by a *newer* release counts as current, because migrations are backward-compatible one release back:
an older replica keeps serving during a rolling update. A schema *behind* the image is not ready, which is what a
one-shot migration job relies on: replicas started before the job finishes stay out of rotation until it has.

## Migrations and upgrades

The gateway image runs `alembic upgrade head` before starting the server, so
deploying a newer image applies the schema change. Two consequences to plan
for:

- **Every replica runs the migration on boot, and that is safe.** The Alembic
  environment takes a Postgres advisory lock before running, so *N* replicas
  starting together serialise: one migrates, the rest wait and then find
  nothing to do. You do not need a separate migration job. For a long
  migration you may still want one — the waiting replicas are not serving yet —
  in which case run `alembic upgrade head` as a pre-deploy step and start the
  replicas after it.
- **Migrations are written to be backward-compatible one release back**, so old
  replicas keep working against the new schema during a rolling update. This is
  an authoring convention, not something enforced by a test — read the
  migration when skipping a version.

Live session records in Valkey carry a schema version. A release reads the
previous release's records or treats them as expired, which makes the client
re-initialise rather than fail.

Because there are no versioned releases yet (see
[Get the images](#get-the-images)), "read the release notes" means reading
`git log` between the commit you deployed and the one you are deploying,
looking for new files under
`packages/bundlemcp/bundlemcp/infrastructure/postgres/migrations/versions/`.

### Upgrading past the endpoint-profile rename

Revision `0009` renames the endpoint profiles for what they change: `claude` becomes `oauth_only` and `chatgpt`
becomes `write_as_read`. It rewrites the profile stored on every endpoint, so existing endpoints keep their URL and
behaviour. It is the one exception to the backward-compatibility convention above: an older replica cannot read a
rewritten endpoint. For this upgrade:

1. Stop every old gateway replica before starting the new ones; do not roll.
2. Edit any [bootstrap file](/self-hosting/bootstrap) or script that names `profile: claude` or `profile: chatgpt` to
   use `oauth_only` or `write_as_read`. The old names are rejected with a validation error that lists the accepted
   ones.

To roll back, run `alembic downgrade 0008`, which restores the old names, and then deploy the previous image.

### Upgrading to per-endpoint browser origins

Revision `0011` gives every endpoint `allowed_origins`. Endpoints that need a credential get `["*"]` and behave as
before. An open endpoint (`auth_modes: ["none"]`) gets `[]`: a browser page on another site that called it is refused
with `403` from now on, until you list that site's origin on the endpoint. Scripts and other clients that are not
browsers are unaffected. The revision only adds a column, so rolling replicas is fine.

## Scaling out

Run more gateway replicas behind the proxy. There is no sticky-session requirement: handshake-era sessions live in
Valkey, modern-era requests carry everything they need. Rate limits are counted in Valkey, so they hold across replicas.

The one exception is a **live stream**: a handshake-era client's `GET` event stream, or a modern client's
`subscriptions/listen`, is pinned to the replica holding the connection. The signal bus in Valkey routes notifications
to it. Nothing about that requires proxy configuration, but it is why Valkey must be one shared instance, not one per
replica.

Two facts about a single replica, since they set the shape of a deployment:

- **One container is one uvicorn process with one worker.** Scale out by adding
  replicas, not workers; there is no worker-count setting.
- **The container always listens on 8000.** No environment variable changes it;
  remap at the proxy or in the container's port mapping.

## Upstreams that scale to zero

An upstream that scales to zero when idle — a Deployment behind the KEDA HTTP add-on, Knative, or a similar interceptor
— is woken by any request that reaches it. The gateway answers most client traffic without contacting upstreams:

| Request or event | Contacts the upstream | Does not |
|---|:---:|:---:|
| `initialize`, `server/discover` | | ✔ |
| `tools/list` (served from the tool cache) | | ✔ |
| `tools/call` for one of the upstream's tools | ✔ | |
| `prompts/*`, `resources/*`, `completion/complete`, for a server that advertised `prompts`, `resources` or `completions` when it was last discovered | ✔ | |
| The same methods for a server that did not advertise them | | ✔ |
| The bundle's own prompts and resources | | ✔ |
| Creating a server | ✔ | |
| Updating a server in a way that changes how it is reached (URL, headers, auth settings) | ✔ | |
| Updating a server whose last probe failed | ✔ | |
| Re-applying an unchanged definition to a working server (API or bootstrap file) | | ✔ |
| The periodic refresh, every `BUNDLEMCP_DISCOVERY_REFRESH_INTERVAL` seconds | ✔ | |
| A gateway restart | | ✔ |
| `:refresh-tools` and `:inspect` | ✔ | |
| Completing an upstream OAuth connect | ✔ | |

To keep idle upstreams at zero:

- **Set `BUNDLEMCP_DISCOVERY_REFRESH_INTERVAL=0`, which turns the periodic refresh off.** Leaving the variable unset
  does not: unset means the default of 1800 seconds, so the refresh would wake every server once every 30 minutes. The
  cost of turning it off: a change to an upstream's tools reaches the cache only through `:refresh-tools`, or when the
  server's definition changes.
- **Keep the bootstrap file or deploy tooling stable.** Re-applying it is free; changing a server's URL, headers or auth
  settings in it wakes that server once on the next start.
- **Expect servers that serve prompts or resources to be woken by clients that list them.** Many clients, claude.ai
  among them, list prompts and resources right after connecting. Those lists are read live from every server that
  advertises them. Context a bundle needs only for its own purpose can be written on the bundle instead, as
  [its own prompts and documents](/manage/bundles#bundle-prompts-and-documents), which wake nothing.

## Backups

Postgres holds **all** durable state: configuration, users, OAuth clients and tokens, upstream tokens, the audit log. A
`pg_dump` of the database is a complete backup.

Against a managed Postgres, point `pg_dump` at the same database the gateway
uses. Note that `BUNDLEMCP_DATABASE_URL` carries a `+asyncpg` driver suffix that
libpq does not understand, so strip it:

```bash
pg_dump "$(echo "$BUNDLEMCP_DATABASE_URL" | sed 's|+asyncpg||')" \
  > bundlemcp-$(date +%F).sql
```

On the dev compose stack, where Postgres is a container:

```bash
docker compose -f deploy/docker-compose.yml exec postgres \
  pg_dump -U bundlemcp bundlemcp > bundlemcp-$(date +%F).sql
```

### Rehearsing the restore

A backup nobody has restored is a hypothesis. The rehearsal is five steps:

```bash
# 1. a scratch database
createdb bundlemcp_restore_test
# 2. load the dump
psql bundlemcp_restore_test < bundlemcp-2026-09-18.sql
# 3. point a gateway at it, with the same encryption keys as the original
BUNDLEMCP_DATABASE_URL=postgresql+asyncpg://…/bundlemcp_restore_test \
BUNDLEMCP_TOKEN_ENCRYPTION_KEYS='["…"]' \
  docker run --rm -p 8001:8000 --env-file restore.env your-registry/bundlemcp-gateway:$SHA
# 4. readiness, which also proves migrations applied
curl -fsS http://localhost:8001/readyz
# 5. one real tool call through a restored endpoint, and an upstream-OAuth
#    server's connection if you have one — that is what proves the keys match
```

Migrations bring the schema forward if the dump is older than the running
version, so step 4 failing usually means a migration did not apply rather than
a bad dump.

The project rehearses this on every release:
[`deploy/rehearse_restore.py`](https://github.com/wingfold-ai/bundlemcp/blob/main/deploy/rehearse_restore.py) runs the
five steps against the compose stack, with a key minted just before the dump so the tool call only succeeds if the data
was restored, and the *Restore rehearsal* workflow runs it for every release tag, before anything is published, or on
demand. To rehearse against your own compose checkout:

```bash
docker compose -f deploy/docker-compose.yml up -d --build --wait
uv run python deploy/rehearse_restore.py
```

Valkey is deliberately **not** backed up. It holds sessions and counters; losing it means clients re-initialise and
rate-limit windows restart.

Keep the token encryption keys and the OIDC client secret with the dump. A restored database whose upstream tokens were
encrypted with a key you no longer have cannot use those connections.

## Network egress

The gateway makes outbound HTTP requests to server URLs, to upstream OAuth providers, to client metadata documents and
to your identity provider. All of them go through one egress policy:

- link-local and cloud metadata ranges (`169.254.0.0/16`, `fe80::/10` and
  AWS's IPv6 metadata address `fd00:ec2::254`), the gateway's own loopback, and
  the unspecified addresses that reach it (`0.0.0.0/8`, `::`) are blocked by
  default; an IPv4-mapped IPv6 address such as `::ffff:169.254.169.254` is
  judged as the IPv4 address it maps;
- private RFC 1918 ranges are allowed, since compose and cluster networks
  are the common case;
- `BUNDLEMCP_EGRESS_ALLOW_CIDRS` widens and `BUNDLEMCP_EGRESS_DENY_CIDRS`
  narrows the policy.

**The allow list is evaluated first and wins outright**, including over the
built-in blocks. An allow entry covering `169.254.0.0/16` — or `0.0.0.0/0` —
re-opens the cloud-metadata range. That is deliberate, because it is what lets
an identity provider on loopback work (a dev Keycloak on the same host needs
exactly this), but it means the allow list is a security-critical setting: keep
it as narrow as the one host you meant to reach.

The policy is enforced **when each connection is opened**. The gateway resolves
the hostname once, tests every address it gets back, and connects to a vetted
address itself, so a name cannot smuggle a blocked IP past a name-based check,
and a DNS answer that changes after the check (DNS rebinding) is never
connected to. TLS still verifies the certificate against the hostname. The MCP
client follows a redirect only within the upstream's own origin, and the
connection that redirect opens is judged the same way. The gateway's outbound
clients ignore `HTTP_PROXY` and the other proxy variables, so a proxy cannot
route around the policy. The one outbound client outside it is the metering
hook's, whose URL is your own configuration.

## Checklist

- [ ] `BUNDLEMCP_PUBLIC_URL` is the HTTPS URL clients reach.
- [ ] `BUNDLEMCP_TRUSTED_PROXIES` names the proxy.
- [ ] Identity provider configured, redirect URI registered, admin emails set.
- [ ] Every secret replaced; `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` set if any server uses upstream OAuth.
- [ ] `BUNDLEMCP_WEB_ORIGINS` contains the admin UI origin.
- [ ] `BUNDLEMCP_BOOTSTRAP_STRICT=true` if you provision from a bootstrap file.
- [ ] `/readyz` wired into the proxy and orchestrator.
- [ ] Postgres backups scheduled and a [restore rehearsed](#rehearsing-the-restore).
- [ ] Proxy allows 4 MiB bodies, 1800 s reads, and does not buffer.
- [ ] `audit_retention_days` set longer than any billing reconciliation window.
- [ ] `BUNDLEMCP_EGRESS_ALLOW_CIDRS` reviewed — it overrides the built-in blocks.

## Limits

| | Value |
|---|---|
| Request body | `max_request_bytes` 4 MiB, `413` above it |
| One upstream message | `max_upstream_response_bytes` 16 MiB; a larger tool result becomes an error |
| Single tool call | `call_timeout` 60 s, ceiling `max_total_timeout` 1800 s |
| Session idle expiry | `session_lifetime` 86 400 s |
| Tool-list cache hint | `list_cache_ttl_ms` 300 000 ms |
| Rate limits | per endpoint, fixed window, counted in Valkey |
| Auth-failure lockout | 20 failures per 300 s per IP |
| Process model | one uvicorn worker per container, port 8000 |
| Audit growth | one row per tool call, kept for `audit_retention_days` (90) |

The runtime-tunable values are the ones with names; see
[Configuration](/self-hosting/configuration#runtime-settings).

## Next steps

- [Operations](/self-hosting/operations) — what to watch day to day.
- [Troubleshooting](/self-hosting/troubleshooting) — symptom-first fixes.
- [Configuration](/self-hosting/configuration) — every setting.
