# Functional testing the full stack

## Prerequisites

- Docker Engine + compose plugin.
- No `/etc/hosts` entry: the compose file pins `KC_HOSTNAME` so Keycloak advertises `http://localhost:8080` to the
  browser while the gateway keeps reaching it at `http://keycloak:8080` over the compose network.
- `deploy/.env` copied from `deploy/.env.example`.

## Bring the stack up

```bash
# gateway, web, Postgres, Valkey, Keycloak and the demo upstreams (echo-mcp, oauth-demo, introspect-demo)
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build --wait
```

Services: gateway :8000, web UI :3000, Keycloak :8080 (admin/admin). `seed.yaml` registers echo, oauth-demo and
introspect-demo and exposes endpoints `demo` (api_key), `claude` and `chatgpt` (oauth), and `passthrough` (oauth +
api_key) for introspect-demo.

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

CI runs every integration test and every browser scenario against this same stack.

## Header passthrough to an introspecting upstream

`introspect-demo` (`examples/introspect-demo-mcp`) stands in for an upstream that verifies its callers itself: it
introspects the bearer the gateway forwards (AUTH-27, AUTH-30) back at the gateway's `/oauth/introspect`, with the
service key as its client secret, and refuses any request whose bearer is not active. Discovery has no caller, so the
seed gives it a static `authorization` header with the dev service key, which introspects as an `api_key:<id>` caller
(AUTH-5). Its `whoami` tool reports the subject the gateway vouched for, the injected `X-MCP-User` (AUTH-29), the
mapped `x-tenant-id → x-tenant` header, and the names of the headers that arrived;
`tests/integration/test_header_passthrough.py` checks each of them through the `passthrough` endpoint.
