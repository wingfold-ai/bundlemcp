# 14 — Endpoints

**Status:** Accepted · **Origin:** improvement (metamcp: 1 endpoint ↔ 1 namespace; bundlemcp: N endpoints per bundle)
**Prior art:** `../metamcp/apps/backend/src/routers/public-metamcp/`, `endpoints` table

## Summary

An endpoint is a public URL serving one bundle over **Streamable HTTP**. The
key upgrade over metamcp: a bundle can have **many endpoints**, each with its
own auth configuration, profile, and rate limits — one bundle, per-client
surfaces (claude.ai vs ChatGPT vs internal scripts).

## Requirements

- **EP-1** URL scheme: `POST/GET/DELETE https://<host>/{endpoint_name}/mcp`
  (Streamable HTTP per current MCP spec). `endpoint_name` is globally unique
  and slug-safe. No SSE (`/sse`) and no REST bridge (`/api`) routes exist
  (decision log).
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

## Out of scope

- Custom domains per endpoint (operator's reverse proxy concern).

## Open questions

- Whether `GET /{endpoint_name}/mcp` (server-initiated stream) is required by
  current claude.ai/ChatGPT clients or can 405 in v1 — decide against real
  client behavior during implementation.
