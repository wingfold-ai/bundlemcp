# 40 — Management REST API

**Status:** Accepted · **Origin:** new (fixes ultra-mcp's biggest integration wart)
**Prior art (the wart):** `../ultra-mcp/packages/registrar/registrar/clients.py` — cookie-replay login + hand-crafted tRPC batch calls, because metamcp had no service API

## Summary

Everything the admin UI can do is available as a versioned, OpenAPI-documented
REST API under `/api/v1`, authenticated by admin session **or** service API
key. The Nuxt UI is a client of this API — there is no privileged side
channel — which guarantees automation parity (ultra-mcp's registrar, CI,
scripts).

## Requirements

- **API-1** Base path `/api/v1`; resources: `servers`, `servers/{id}/tools`,
  `bundles`, `bundles/{id}/servers`, `bundles/{id}/tools`, `endpoints`,
  `api-keys`, `users`, `audit-records`, `config`, `profiles` (read-only,
  [PROF-5](15-endpoint-profiles.md)), plus action routes (e.g.
  `servers/{id}:refresh-tools`, `servers/{id}:probe`).
- **API-2** Auth: admin browser session ([21-admin-auth.md](21-admin-auth.md))
  or `service`-kind API key ([KEY-2](22-api-keys.md)) via `Authorization`
  header. All routes require one of the two; 401/403 are structured.
- **API-3** DTOs are Pydantic models derived from the SQLModel entities
  ([ARC-3](01-architecture.md)); OpenAPI schema served at
  `/api/v1/openapi.json` and used to generate the frontend client
  ([ARC-4](01-architecture.md)).
- **API-4 Registrar use case** (the contract replacing the tRPC hack):
  `PUT /api/v1/servers/{name}` is a **config-only upsert** — create-or-update
  by name, idempotent, returning the server including current tool cache.
  It never blocks on probing the upstream ([SRV-2](10-server-registry.md)
  allows registering not-yet-started servers), so a discovery loop can
  converge by repeatedly PUTting desired state. The DTO tolerates an optional
  `transport` field but accepts only `streamable-http` (422 with a pointed
  message otherwise) — so registrar payloads carrying the field don't break.
- **API-5** Mutations are validated (Pydantic + domain rules from the owning
  specs) and return the canonical resource representation; list routes
  support pagination (default page size 50, max 500, stable ordering by
  creation time then id) and the filters the UI needs.
- **API-7** Browser-facing security: CORS/CSRF per
  [SEC-4](70-security.md). Consent revocation ([OAS-11](20-oauth-server.md))
  and user deactivation ([ADM-6](21-admin-auth.md)) are exposed as routes.
- **API-6** Write operations SHOULD be safely retryable: upserts by natural
  key where sensible (API-4), deletes idempotent (404 → 204 semantics
  documented per route).

## Out of scope

- GraphQL/tRPC surfaces.
- Webhooks/event subscriptions (possible later addition; poll `audit-records`
  and resource `updated_at` for now).

## Open questions

- None.
