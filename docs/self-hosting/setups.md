# Local, tunnel or production

There are three ways to run bundlemcp, and only the last one is meant for other people to use. This page says what each
one is for, what it leaves insecure, and which settings a real deployment has to provide.

| Setup | For | Reachable from | How |
|---|---|---|---|
| **Local** | Trying the admin UI, scripts and agents on your own machine | Your machine only | `docker compose … up` — the [Quickstart](/guide/quickstart) |
| **Local + tunnel** | Testing with claude.ai, ChatGPT or Claude Desktop before you deploy | Anyone with the tunnel URL | `deploy/stack.sh up` — [below](#local-tunnel) |
| **Production** | Real users | Your domain, over HTTPS | Your own compose file or orchestrator — [Production deployment](/self-hosting/deploy) |

## What the two local setups take shortcuts on

Both local setups run the compose stack in `deploy/`, which is built to start with one command, not to be safe. It:

- **ships its secrets inline.** The service key `bmcp_sk_devservicekey…`, the token encryption key and the identity
  provider's client secret are the same in every checkout. Anyone who knows the repository knows them.
- **brings a development identity provider.** Keycloak with the login `admin` / `admin`, and a realm that accepts any
  redirect URI so that a tunnel's changing URL still works.
- **speaks plain HTTP** on `localhost`. In the tunnel setup the tunnel adds HTTPS in front.
- **trusts every private address as a proxy**, so `X-Forwarded-*` headers from inside the compose network are believed.
- **lets the gateway reach its own loopback**, because the OAuth demo upstream runs there. A production gateway never
  allows that.

None of that matters while only you can reach the stack. A tunnel makes it reachable from the internet, so keep a tunnel
up only while you are testing, and never put data you care about into it.

## Local + tunnel {#local-tunnel}

claude.ai and ChatGPT connect to an MCP server **from their own servers on the internet**, so `http://localhost:8000` is
useless to them: they need a public HTTPS URL. A tunnel provides one. It is a small program that opens an outgoing
connection to a tunnel service, which then forwards requests for a public URL back to your machine.

`deploy/stack.sh` sets this up. It starts the same stack as the quickstart, adds a reverse proxy (Caddy) that serves the
gateway and the admin UI under one address, and a tunnel in front of the proxy:

```bash
cp deploy/.env.example deploy/.env    # once; TUNNEL=quick is the default
deploy/stack.sh up                    # or: make up
```

When it is done it prints the public URL and the connector URLs:

```text
bundlemcp is up.

  Admin UI         https://<random-words>.trycloudflare.com
  Gateway          https://<random-words>.trycloudflare.com
  ...
  claude.ai / Claude Desktop connector URL:   https://<random-words>.trycloudflare.com/claude/mcp
  ChatGPT connector URL:                      https://<random-words>.trycloudflare.com/chatgpt/mcp
```

Paste the connector URL into claude.ai or ChatGPT, as described in [Connect claude.ai](/connect/claude) and
[Connect ChatGPT](/connect/chatgpt). The seed already has an endpoint for each.

### Why the script and not just `cloudflared`

The gateway has to know its public URL **before it starts**: every OAuth address it hands to claude.ai or ChatGPT —
issuer, authorization URL, token URL, redirect URI — is built from `BUNDLEMCP_PUBLIC_URL`. A client that is sent to
`http://localhost:8000` for login cannot follow. The script starts the tunnel first, reads the URL the tunnel was given,
and only then starts the gateway with that URL. Starting a tunnel by hand in front of a running stack skips that step
and breaks every OAuth login.

### Choosing a tunnel

`TUNNEL` in `deploy/.env` selects it:

| `TUNNEL` | What you get | What you need |
|---|---|---|
| `quick` (default) | A Cloudflare quick tunnel: a random `https://….trycloudflare.com` URL | Nothing — no account |
| `ngrok` | ngrok with a static domain: the same URL every time | `NGROK_AUTHTOKEN` and `NGROK_DOMAIN` from the ngrok dashboard (the free plan includes one domain) |
| `none` | No tunnel; the stack stays on `localhost` | Nothing |

A quick tunnel's URL changes whenever the tunnel container restarts. Run `deploy/stack.sh up` again afterwards so the
gateway learns the new URL, and reconnect claude.ai or ChatGPT, which remembered the old one. If that happens often, use
ngrok's static domain.

### Everyday commands

| Command | Does |
|---|---|
| `deploy/stack.sh url` | Prints the URL the stack is published at, and warns if the tunnel has moved since |
| `deploy/stack.sh logs` | Follows the logs of every container |
| `deploy/stack.sh down` | Stops everything; the database is kept |
| `deploy/stack.sh rebuild` | Deletes the stack's data volumes, rebuilds the images and starts fresh from the seed |

Every command has a `make` alias (`make up`, `make url`, …).

::: warning Signing in through the tunnel works on this machine only
The development identity provider is published at `http://localhost:8080`. When you sign in — to the admin UI through
the tunnel URL, or during claude.ai's OAuth flow — your browser is sent there, which only works in a browser on the
machine running the stack. A production deployment uses an identity provider with its own public URL.
:::

## Production

A production deployment replaces every shortcut above. [Production deployment](/self-hosting/deploy) walks through the
reverse proxy, health checks, backups and scaling. These are the settings it must provide; the
[Configuration reference](/self-hosting/configuration) lists every other one with its default.

### Gateway: always set

| Variable | Set it to | Why |
|---|---|---|
| `BUNDLEMCP_DATABASE_URL` | `postgresql+asyncpg://<user>:<password>@<host>:5432/<db>` | Where configuration, tokens and the audit log are kept |
| `BUNDLEMCP_REDIS_URL` | `redis://<host>:6379/0` | Where live sessions, rate-limit counters and cross-replica signals are kept |
| `BUNDLEMCP_PUBLIC_URL` | The HTTPS URL clients reach, e.g. `https://mcp.example.com` | Every OAuth address and the login cookie derive from it |
| `BUNDLEMCP_TRUSTED_PROXIES` | The CIDRs your reverse proxy connects from, e.g. `["10.0.0.0/8"]` | Without it, rate limits and audit records see every request as coming from the proxy |
| `BUNDLEMCP_OIDC_DISCOVERY_URL` | Your identity provider's `…/.well-known/openid-configuration` | People sign in there ([Identity provider](/self-hosting/identity-provider)) |
| `BUNDLEMCP_OIDC_CLIENT_ID` | The client id you registered for the gateway | Same |
| `BUNDLEMCP_OIDC_CLIENT_SECRET` | The secret your identity provider issued | Same |
| `BUNDLEMCP_ADMIN_EMAILS` | `["you@example.com"]` | Who gets admin rights |
| `BUNDLEMCP_INITIAL_SERVICE_KEY` | A key you generate (below) | Lets you use the management API before anyone has signed in; ignored once a service key exists |

### Gateway: set when it applies

| Variable | When | Set it to |
|---|---|---|
| `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` | Any upstream server uses upstream OAuth | `["<fernet key>"]` you generate (below) — keep it: losing it disconnects every stored account |
| `BUNDLEMCP_WEB_ORIGINS` | The admin UI runs on a different origin than the gateway | `["https://admin.example.com"]` |
| `BUNDLEMCP_BOOTSTRAP_FILE` | You provision from a [bootstrap file](/self-hosting/bootstrap) | Its path inside the container |
| `BUNDLEMCP_BOOTSTRAP_STRICT` | Same | `true`, so a broken file stops the start instead of being logged |
| `BUNDLEMCP_DCR_ALLOWED_REDIRECT_URIS` | You know which clients will connect | Their OAuth callback URLs, e.g. `["https://claude.ai/api/mcp/auth_callback"]` |
| `BUNDLEMCP_EGRESS_ALLOW_CIDRS` | Upstream servers sit on addresses the gateway blocks by default | Only those ranges — the list overrides the built-in blocks ([Network egress](/self-hosting/deploy#network-egress)) |

### Admin UI container

| Variable | Set it to |
|---|---|
| `NUXT_PUBLIC_API_BASE` | The gateway's public URL, the same value as `BUNDLEMCP_PUBLIC_URL` |

### Generating the secrets

```bash
# a service API key
python3 -c "import secrets; print('bmcp_sk_' + secrets.token_urlsafe(32))"
# a token encryption key (Fernet: url-safe base64 of 32 random bytes)
openssl rand -base64 32 | tr '+/' '-_'
```

Keep both in your platform's secret store, never in the repository. The [Secrets](/self-hosting/deploy#secrets) section
says how to rotate them.
