# 40 — Management REST API

**Status:** Accepted · **Origin:** new (fixes the first consumer's biggest integration wart) **Prior art (the wart):**
the first consumer's registrar client — cookie-replay login + hand-crafted tRPC batch calls, because metamcp had no
service API

## Summary

Everything the admin UI can do is available as a versioned, OpenAPI-documented REST API under `/api/v1`, authenticated
by admin session **or** service API key. The Nuxt UI is a client of this API — there is no privileged side channel —
which guarantees automation parity (the application layer's registrar, CI, scripts).

## Requirements

- **API-1** Base path `/api/v1`; resources: `upstreams`, `upstreams/{id}/tools`, `bundles`,
  `bundles/{id}/upstreams` ([SRV-16](10-server-registry.md)), `bundles/{id}/tools`, `endpoints`, `api-keys`,
  `users`, `audit-records`, `config`, `profiles` (read-only, [PROF-5](15-endpoint-profiles.md)), plus action routes
  (e.g. `upstreams/{id}:refresh-tools`, `upstreams/{id}:probe`), and `me` (caller identity for the UI:
  kind, email, `is_admin` — answers 200 for any active signed-in session, admin or not, so the UI can render its "no
  access" page ([UI-2](60-admin-ui.md)); service keys get their key identity), and `me/endpoints` — the catalogue for
  that same audience: every enabled endpoint accepting `oauth`, with its connection URL and the bundle's description, so
  a signed-in non-admin finds what to connect an MCP client to without any privileged call.
- **API-2** Auth: admin browser session ([21-admin-auth.md](21-admin-auth.md)) or `service`-kind API key
  ([KEY-2](22-api-keys.md)) via `Authorization` header. All routes require one of the two; 401/403 are structured.
- **API-3** DTOs are Pydantic models derived from the SQLModel entities ([ARC-3](01-architecture.md)); OpenAPI schema
  served at `/api/v1/openapi.json` and used to generate the frontend client ([ARC-4](01-architecture.md)).
- **API-4 Registrar use case** (the contract replacing the tRPC hack): `PUT /api/v1/upstreams/{name}` is a
  **config-only upsert** — create-or-update by name, idempotent, returning the server including current tool cache. It
  never blocks on probing the upstream ([SRV-2](10-server-registry.md) allows registering not-yet-started servers), so a
  discovery loop can converge by repeatedly PUTting desired state. The DTO tolerates an optional `transport` field but
  accepts only `streamable-http` (422 with a pointed message otherwise) — so registrar payloads carrying the field don't
  break.
- **API-5** Mutations are validated (Pydantic + domain rules from the owning specs) and return the canonical resource
  representation; list routes support pagination (default page size 50, max 500, stable ordering by creation time then
  id) and the filters the UI needs.
- **API-7** Browser-facing security: CORS/CSRF per [SEC-4](70-security.md). Consent revocation
  ([OAS-11](20-oauth-server.md)) and user deactivation ([ADM-6](21-admin-auth.md)) are exposed as routes.
- **API-6** Write operations SHOULD be safely retryable: upserts by natural key where sensible (API-4), deletes
  idempotent (404 → 204 semantics documented per route).
- **API-8 Deprecated route aliases.** A renamed route keeps answering at its old path for a deprecation window, with
  identical behaviour, request and response bodies. Every response from an old path carries `Deprecation` (RFC 9745,
  the date the alias was deprecated), `Sunset` (RFC 8594, the date it stops answering) and
  `Link: <new path>; rel="successor-version"`; each use is logged at `WARN` once per caller identity per hour and
  counted in a `deprecated_route_requests` metric labelled by route, so an operator can see which automation still has
  to move. Old paths are left out of the OpenAPI document, so generated clients only learn the new ones. The window is
  at least 180 days from the first release that ships the new path, and never shorter than one minor release; after the
  sunset date the old path answers `410 Gone` with the new path in the problem body for one further minor release, then
  `404`. The first use is the `servers` → `upstreams` rename ([SRV-16](10-server-registry.md),
  [ADR-0045](../docs/adr/0045-upstreams-on-the-published-surface.md)).

## Out of scope

- GraphQL/tRPC surfaces.
- Webhooks/event subscriptions (possible later addition; poll `audit-records` and resource `updated_at` for now).

## Open questions

- None.
