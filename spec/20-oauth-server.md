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
  by default, redirect URIs validated (https or localhost); an
  `application_type` sent by the client is accepted and stored. A
  registration the server cannot honour is refused with HTTP 400 and the
  RFC 7591 error code, never the framework's validation shape: an
  unsupported grant type, response type, auth method or application type,
  or a body that is not valid JSON, is `invalid_client_metadata`; a redirect
  URI that fails the rule above is `invalid_redirect_uri`. The implicit and
  password grants stay unsupported: OAuth 2.1 removed them, and MCP clients
  use the authorization code grant with PKCE. MCP 2026-07-28
  deprecates DCR in favour of Client ID Metadata Documents (OAS-13); it stays
  supported for clients that have not moved (ChatGPT, Claude as of 2026-09).
- **OAS-3 Authorization code + PKCE**: `GET /oauth/authorize` requires an
  authenticated browser session — if absent, redirect into the OIDC login and
  return to complete the flow. S256 PKCE REQUIRED for public clients. Codes
  are single-use, 10-minute expiry, bound to client + redirect URI + challenge.
  The burn is atomic (a compare-and-set on the stored code), so two
  redemptions racing on one code yield one token pair.
- **OAS-4 Token endpoint**: `POST /oauth/token` supports `authorization_code`
  and `refresh_token` grants. Access tokens are opaque (`bmcp_…` prefix),
  default 1h lifetime; refresh tokens default 7d and are **rotated on every
  use** (old one revoked). A refresh token presented again after rotation is
  treated as stolen: every pair descended from the same authorization grant
  (the token *family*) is revoked (RFC 9700 §4.14.2). Lifetimes
  runtime-configurable (`Config`). The grant types a client registered
  (OAS-2) or its metadata document declares (OAS-13) are honoured: a grant
  outside that list is refused with `unauthorized_client`, and so is an
  authorization request from a client that did not register
  `authorization_code`.
- **OAS-5 Introspection** (RFC 7662): `POST /oauth/introspect` returns
  `active`, `sub` (bundlemcp user id — the stable billing key, see
  [02-domain-model.md](02-domain-model.md) `User`), `client_id`, `exp`,
  `scope`. Callable by upstream services; protected against anonymous
  fishing (requires a valid API key, service token, or client credentials —
  a service key supplied as the RFC 7662 HTTP-Basic client secret counts).
  Gateway **API keys** presented as the introspected token are reported as
  `active` with `sub` `api_key:<id>` ([FWD-3](24-identity-forwarding.md)
  identity format), so introspecting upstreams ([FWD-4](24-identity-forwarding.md))
  can serve api_key-authenticated callers and tool discovery of such
  upstreams can authenticate via a static `authorization` header.
- **OAS-6 Revocation** (RFC 7009): `POST /oauth/revoke` for access and
  refresh tokens. The client authenticates as at the token endpoint (a
  public client by `client_id` alone) and may revoke only tokens issued to
  it; a token that is unknown or another client's is answered 200 and left
  alone. Authentication failures count toward the [RATE-5](16-rate-limiting.md)
  lockout.
- **OAS-7** Resource-server validation of bearer tokens on endpoints MUST be a
  **direct database/Redis lookup**, not an HTTP self-call to the introspection
  route (metamcp anti-pattern: it introspected itself over HTTP per request).
- **OAS-8** Token values stored hashed ([DOM-3](02-domain-model.md)); expired
  codes/tokens purged by a periodic job.
- **OAS-9** The full claude.ai happy path MUST be covered by an integration
  test: register → authorize (OIDC login) → code → token → MCP initialize →
  tools/list → tools/call → refresh → introspect.
- **OAS-10 Endpoint-bound tokens (RFC 8707):** the authorize and token
  requests accept a `resource` parameter identifying the target endpoint
  (its canonical `/{endpoint_name}/mcp` URL); issued codes and tokens are
  bound to that endpoint as **audience** (`OAuthAccessToken.endpoint_id`,
  [02-domain-model.md](02-domain-model.md)) and are accepted **only there**
  ([EP-3a](14-endpoints.md)). Requests without `resource` default to the
  endpoint whose protected-resource metadata initiated the flow; a token is
  never valid across endpoints. Introspection (OAS-5) reports the audience.
- **OAS-11 Consent:** the authorize flow shows a consent screen (client name
  + target endpoint + requested scope) before issuing a code. Consent is
  persisted per `(user, client, endpoint)` (`OAuthConsent`) and skipped while
  unrevoked; users/admins can revoke consent (UI + management API), which
  also revokes tokens issued under it. Consent pages carry the
  [SEC-6](70-security.md) hardening headers.
- **OAS-12** Dynamic client registration abuse controls per
  [SEC-8](70-security.md).
- **OAS-13 Client ID Metadata Documents:** a `client_id` that is an `https://`
  URL identifies a client by its metadata document. The authorize endpoint
  fetches the document (through the egress policy, [SEC-1](70-security.md)),
  requires its `client_id` to echo the URL, validates `redirect_uris` against
  it, and caches it for its `Cache-Control` lifetime (bounded, default 1 h) in
  the RESP store. Such clients need no registration; consent (OAS-11) shows the
  document's `client_name`. Advertised via
  `client_id_metadata_document_supported: true` in OAS-1 metadata.
- **OAS-14 Issuer identification (RFC 9207):** every authorization response,
  including error redirects, carries `iss=<issuer>`, and OAS-1 metadata sets
  `authorization_response_iss_parameter_supported: true`.

## Out of scope

- Acting as a general-purpose IdP (no ID tokens/OIDC provider surface beyond
  what MCP clients need; human identity always comes from the external IdP).
  This includes `/oauth/userinfo` (metamcp served one) — introspection's
  `sub` covers the known consumers; consciously skipped.
- Scopes/permissions granularity beyond a single default scope in v1
  (endpoint binding is via audience, not scopes).

## Open questions

- ~~Whether resource-indicator (RFC 8707) support is needed.~~ **Resolved:**
  required — OAS-10. Still verify during implementation whether claude.ai
  additionally needs `client_credentials`; extend OAS-4 if so.
