# 20 — OAuth 2.1 server (for MCP clients)

**Status:** Accepted · **Origin:** metamcp carry-over (hardened)
**Prior art:** `../metamcp/apps/backend/src/routers/oauth/` (registration, authorization, token, metadata), `../metamcp/README-oauth.md`

## Summary

bundlemcp runs its own OAuth 2.1 authorization server so MCP clients —
claude.ai above all — can connect to protected endpoints with zero manual
client setup. End-user login inside the authorize flow is **federated to the
external OIDC IdP** ([21-admin-auth.md](21-admin-auth.md)); bundlemcp issues
its own opaque tokens and provides introspection so upstreams and the
application layer can resolve a stable `sub`.

## Requirements

- **OAS-1 Discovery**: serve `/.well-known/oauth-authorization-server` (RFC
  8414) and `/.well-known/oauth-protected-resource` metadata consistent with
  the endpoints' 401 challenges ([EP-3](14-endpoints.md)).
- **OAS-2 Dynamic Client Registration** (RFC 7591): `POST /oauth/register`,
  open registration, public clients (`token_endpoint_auth_method: none`)
  by default, redirect URIs validated (https or localhost).
- **OAS-3 Authorization code + PKCE**: `GET /oauth/authorize` requires an
  authenticated browser session — if absent, redirect into the OIDC login and
  return to complete the flow. S256 PKCE REQUIRED for public clients. Codes
  are single-use, 10-minute expiry, bound to client + redirect URI + challenge.
- **OAS-4 Token endpoint**: `POST /oauth/token` supports `authorization_code`
  and `refresh_token` grants. Access tokens are opaque (`bmcp_…` prefix),
  default 1h lifetime; refresh tokens default 7d and are **rotated on every
  use** (old one revoked). Lifetimes runtime-configurable (`Config`).
- **OAS-5 Introspection** (RFC 7662): `POST /oauth/introspect` returns
  `active`, `sub` (bundlemcp user id — the stable billing key, see
  [02-domain-model.md](02-domain-model.md) `User`), `client_id`, `exp`,
  `scope`. Callable by upstream services; protected against anonymous
  fishing (requires a valid API key, service token, or client credentials).
- **OAS-6 Revocation** (RFC 7009): `POST /oauth/revoke` for access and
  refresh tokens.
- **OAS-7** Resource-server validation of bearer tokens on endpoints MUST be a
  **direct database/Redis lookup**, not an HTTP self-call to the introspection
  route (metamcp anti-pattern: it introspected itself over HTTP per request).
- **OAS-8** Token values stored hashed ([DOM-3](02-domain-model.md)); expired
  codes/tokens purged by a periodic job.
- **OAS-9** The full claude.ai happy path MUST be covered by an integration
  test: register → authorize (OIDC login) → code → token → MCP initialize →
  tools/list → tools/call → refresh → introspect.

## Out of scope

- Acting as a general-purpose IdP (no ID tokens/OIDC provider surface beyond
  what MCP clients need; human identity always comes from the external IdP).
- Scopes/permissions granularity beyond a single default scope in v1.

## Open questions

- Whether claude.ai (July 2026) requires `client_credentials` or
  resource-indicator (RFC 8707) support — verify during implementation and
  extend OAS-4 if needed.
