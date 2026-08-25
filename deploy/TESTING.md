# Functional testing the full stack

## Prerequisites

- Docker Engine + compose plugin.
- `127.0.0.1 keycloak` in `/etc/hosts` — the gateway hands browsers Keycloak
  URLs under the compose-internal hostname, so the host must resolve it:
  `echo "127.0.0.1 keycloak" | sudo tee -a /etc/hosts`.
- `deploy/.env` copied from `deploy/.env.example`. For the seo-gsc flow fill
  in `GSC_GOOGLE_CLIENT_ID/SECRET` (Google Cloud OAuth "Web application"
  client with the Search Console scope and redirect URI
  `http://localhost:8001/google/callback`), `GSC_TOKEN_ENCRYPTION_KEY`
  (Fernet key) and `GSC_SIGNING_KEY` (`openssl rand -hex 32`). DataForSEO
  credentials are optional — without them the server boots but calls 401.

## Bring the stack up

```bash
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
```

Services: gateway :8000, web UI :3000, Keycloak :8080 (admin/admin),
seo-gsc :8001, SeaweedFS :8333. The seed registers echo + the application-layer fleet
and exposes endpoints `demo` (api_key), `seo` and `media` (oauth + api_key).

## Test suites

```bash
# hermetic unit tests (no stack needed)
uv run pytest -q

# API-level integration (needs the stack)
BUNDLEMCP_INTEGRATION=1 uv run pytest tests-integration -q

# browser UI tests (needs the stack; logs in via Keycloak admin/admin)
cd apps/web && npx playwright test
```

## Connecting Google Search Console (one-time, interactive)

seo-gsc runs its own per-user Google OAuth; the gateway forwards your bearer
(FWD-1) and seo-gsc introspects it back at the gateway (FWD-4, OAS-5). To
link a Google account:

1. Call any `seo-gsc__*` tool through `http://localhost:8000/seo/mcp` with an
   OAuth bearer (e.g. via the `test_gsc_tool_call_reaches_gsc_via_forwarded_bearer`
   integration test, or claude.ai connected to the `seo` endpoint). The reply
   contains seo-gsc's connect instructions with a ticket URL on
   `http://localhost:8001/connect`.
2. Open that URL in a browser and complete the Google consent.
3. Re-run the tool call — it now returns Search Console data for the
   connected account. Tokens are stored encrypted inside seo-gsc, keyed by
   the introspected `sub`.

Note: api_key callers introspect as `api_key:<key-id>` (OAS-5), so a Google
account can also be linked to an API key identity the same way.
