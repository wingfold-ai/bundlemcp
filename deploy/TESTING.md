# Functional testing the full stack

## Prerequisites

- Docker Engine + compose plugin.
- No `/etc/hosts` entry: the compose file pins `KC_HOSTNAME` so Keycloak advertises `http://localhost:8080` to the
  browser while the gateway keeps reaching it at `http://keycloak:8080` over the compose network.
- `deploy/.env` copied from `deploy/.env.example`. For the seo-gsc flow fill in `GSC_GOOGLE_CLIENT_ID/SECRET` (Google
  Cloud OAuth "Web application" client with the Search Console scope and redirect URI
  `http://localhost:8001/google/callback`), `GSC_TOKEN_ENCRYPTION_KEY` (Fernet key) and `GSC_SIGNING_KEY`
  (`openssl rand -hex 32`). DataForSEO credentials are optional — without them the server boots but calls 401.

## Bring the stack up

```bash
# core stack (gateway, web, Postgres, Valkey, Keycloak, echo-mcp, oauth-demo)
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build --wait
# ... plus the fleet (private GHCR images), with BUNDLEMCP_SEED_FILE=seed.fleet.yaml in deploy/.env
docker compose -f deploy/docker-compose.yml --env-file deploy/.env --profile fleet up -d --build --wait
```

Services: gateway :8000, web UI :3000, Keycloak :8080 (admin/admin), seo-gsc :8001, SeaweedFS :8333. `seed.yaml`
registers echo and oauth-demo and exposes endpoints `demo` (api_key), `claude` and `chatgpt` (oauth).
`seed.fleet.yaml` is the same document plus the fleet, with endpoints `seo` and `media` (oauth + api_key); the fleet
integration tests need it.

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
```

## Connecting Google Search Console (one-time, interactive)

seo-gsc runs its own per-user Google OAuth; the gateway forwards your bearer (AUTH-27) and seo-gsc introspects it back
at the gateway (AUTH-30, AUTH-5). To link a Google account:

1. Call any `seo-gsc__*` tool through `http://localhost:8000/seo/mcp` with an OAuth bearer (e.g. via the
   `test_gsc_tool_call_reaches_gsc_via_forwarded_bearer` integration test, or claude.ai connected to the `seo`
   endpoint). The reply contains seo-gsc's connect instructions with a ticket URL on `http://localhost:8001/connect`.
2. Open that URL in a browser and complete the Google consent.
3. Re-run the tool call — it now returns Search Console data for the connected account. Tokens are stored encrypted
   inside seo-gsc, keyed by the introspected `sub`.

Note: api_key callers introspect as `api_key:<key-id>` (AUTH-5), so a Google account can also be linked to an API key
identity the same way.
