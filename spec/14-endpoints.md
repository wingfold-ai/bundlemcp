# 14 — Endpoints

**Status:** Accepted · **Origin:** improvement (metamcp: 1 endpoint ↔ 1 namespace; bundlemcp: N endpoints per bundle)
**Prior art:** `../metamcp/apps/backend/src/routers/public-metamcp/`, `endpoints` table

## Summary

An endpoint is a public URL serving one bundle over **Streamable HTTP**. The
key upgrade over metamcp: a bundle can have **many endpoints**, each with its
own auth configuration, profile, and rate limits — one bundle, per-client
surfaces (claude.ai vs ChatGPT vs internal scripts).

## Requirements

- **EP-1** URL scheme: `POST https://<host>/{endpoint_name}/mcp` (Streamable
  HTTP). `endpoint_name` is globally unique, slug-safe, and MUST NOT be a
  reserved first path segment (`api`, `oauth`, `.well-known`, `healthz`,
  `readyz`, `metrics`, `docs`, `login`, `consent`, `static` — validated at
  write time). No SSE (`/sse`) and no REST bridge (`/api`) routes exist
  (decision log). The one endpoint serves every supported protocol revision
  ([PROT-13](32-protocol-passthrough.md)): modern-era clients (2026-07-28+)
  use POST only; `GET` and `DELETE` without an `Mcp-Session-Id` answer
  `405 Method Not Allowed`.
- **EP-1a** *(handshake-era clients)* `GET /{endpoint_name}/mcp` (the
  server→client event stream) and `DELETE` (session end) MUST be supported for
  a request carrying a valid `Mcp-Session-Id` — the GET stream carries
  list-changed notifications, server→client requests, and out-of-call messages
  required by [32-protocol-passthrough.md](32-protocol-passthrough.md). Modern
  clients obtain the equivalent stream with `subscriptions/listen`
  ([PROT-17](32-protocol-passthrough.md)).
- **EP-2** An endpoint references exactly one bundle; a bundle may have any
  number of endpoints. Deleting a bundle deletes its endpoints
  ([DOM-2](02-domain-model.md)).
- **EP-3** Per-endpoint **auth modes** (`auth_modes`, non-empty set):
  - `oauth` — bearer token issued by bundlemcp's OAuth server
    ([20-oauth-server.md](20-oauth-server.md));
  - `api_key` — `Authorization: Bearer sk_…` or `X-API-Key` header
    ([22-api-keys.md](22-api-keys.md));
  - `none` — public, only valid alone and requires an explicit
    `allow_unauthenticated=true` flag on write.
  A request is accepted if it satisfies **any** configured mode. 401 responses
  MUST include the `WWW-Authenticate` challenge and OAuth protected-resource
  metadata pointers that MCP clients (claude.ai) need for discovery.
- **EP-3a** OAuth bearers are accepted only when the token's audience matches
  this endpoint ([OAS-10](20-oauth-server.md)); audience mismatch is a 401
  with `error="invalid_token"`, prompting the client to re-authorize for this
  endpoint.
- **EP-3b** When a request satisfies multiple modes (e.g. valid OAuth bearer
  *and* API key present), precedence is **oauth > api_key**; the winning
  identity is used consistently for metering, audit, rate limiting, and
  identity forwarding.
- **EP-4** Each endpoint has a `profile` shaping its tool surface
  ([15-endpoint-profiles.md](15-endpoint-profiles.md)) and optional rate
  limits ([16-rate-limiting.md](16-rate-limiting.md)).
- **EP-5** `enabled=false` returns 404 for the endpoint without deleting its
  config.
- **EP-6** The resolved caller identity (user `sub` via OAuth, or API key id)
  MUST be attached to the request context — middleware
  ([31-middleware.md](31-middleware.md)), audit ([50-audit-log.md](50-audit-log.md)),
  and identity forwarding ([24-identity-forwarding.md](24-identity-forwarding.md))
  all read it from there, never from tool arguments.
- **EP-7** Endpoint CRUD via management API and UI, including a copy-paste
  connection card in the UI (URL + auth instructions per client type).
- **EP-8** Renaming an endpoint changes its public URL and breaks every
  connected client. Renames MUST be rejected unless the request carries an
  explicit `force` flag (mirror of [SRV-5](10-server-registry.md)); the UI
  spells out the consequence.
- **EP-9** Request/response size limits per [SEC-7](70-security.md); CORS
  behavior per [SEC-5](70-security.md).

## Out of scope

- Custom domains per endpoint (operator's reverse proxy concern).

## Open questions

- ~~Whether `GET /{endpoint_name}/mcp` can 405 in v1.~~ **Resolved:** required
  (EP-1a) for handshake-era sessions — the full-bidirectional decision depends
  on it; 405 for requests without a session, as MCP 2026-07-28 prescribes.
