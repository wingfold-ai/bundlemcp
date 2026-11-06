# Functional testing the full stack

## Prerequisites

- Docker Engine + compose plugin.
- No `/etc/hosts` entry: the compose file pins `KC_HOSTNAME` so Keycloak advertises `http://localhost:8080` to the
  browser while the gateway keeps reaching it at `http://keycloak:8080` over the compose network.
- Optionally `deploy/.env` copied from `deploy/.env.example`; without it the stack uses its built-in development
  values.

## Bring the stack up

```bash
# gateway, web, Postgres, Valkey, Keycloak, echo-mcp, identity-demo, oauth-demo
docker compose -f deploy/docker-compose.yml up -d --build --wait
```

Services: gateway :8000, web UI :3000, Keycloak :8080 (admin/admin), oauth-demo :9000. `seed.yaml` registers echo,
oauth-demo and identity-demo, and exposes the endpoints `demo` (api_key), `claude` and `chatgpt` (oauth), and
`identity` (oauth + api_key).

## Reach the stack from claude.ai, ChatGPT or Claude Desktop

```bash
deploy/stack.sh up      # or: make up
```

`deploy/stack.sh` starts the core stack behind a Caddy proxy and a tunnel, chosen by `TUNNEL` in `deploy/.env`:
`quick` (default, a Cloudflare quick tunnel, no account, a new `*.trycloudflare.com` URL on every tunnel restart),
`ngrok` (a static domain: `NGROK_AUTHTOKEN` and `NGROK_DOMAIN`), or `none`. It reads the tunnel's URL first and starts
the gateway with it as `BUNDLEMCP_PUBLIC_URL`, so OAuth metadata and redirect URIs match what the client dials.
`deploy/stack.sh url` prints the current URL, `down` stops everything (data stays), `rebuild` starts from empty volumes.

## Test suites

```bash
# hermetic unit tests (no stack needed)
uv run pytest -q

# API-level integration (needs the stack)
BUNDLEMCP_INTEGRATION=1 uv run pytest tests/integration -q

# browser UI tests (needs the stack; logs in via Keycloak admin/admin)
cd apps/web && npx playwright test

# UI unit tests (no stack needed)
cd apps/web && npm test
```

CI runs the same commands against the same stack: every integration test and every browser scenario, with nothing left
out.

## Identity forwarding

`tests/integration/test_identity_forwarding.py` checks what an upstream learns about its caller, against `identity-demo`
(`examples/identity-demo-mcp`). That server refuses requests without a credential, introspects the bearer the gateway
forwards against the gateway's `/oauth/introspect`, and its `whoami` tool reports the introspected caller, the
`X-MCP-User` header and the mapped `x-tenant` header. The tests cover discovery through the static header, an OAuth
user and an API key as callers, a spoofed `X-MCP-User`, header mapping, and callers never seeing each other's identity.
The OAuth tests sign in as `admin` / `admin` through the dev Keycloak realm.

