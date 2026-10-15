# Design

## Context

Since `harden-http-edge`, `PathScopedCors` (api layer, `api/http/path_scoped_cors.py`) answers CORS for
`/{endpoint}/mcp` before routing: any origin is reflected, credentials never allowed. That runs before the endpoint is
known, so it cannot vary by endpoint. The MCP edge resolves the endpoint in `AdmissionGate.admit_caller`
(`api/mcp/routing/admission_gate.py`), one short unit of work that loads the bundle view and then authenticates;
`McpGatewayRouter` (`api/mcp/routing/gateway_router.py`) is the single exit for POST, GET and DELETE. There is no
`OPTIONS` route: the middleware answers preflights. Endpoint upserts are full replaces (`EndpointUpsert`), and an
endpoint's `auth_modes` is either `[none]` alone or a combination of `oauth` and `api_key` (EP-3).

## Goals / Non-Goals

**Goals:**

- The CORS grant and the `Origin` check for MCP routes decided from the endpoint's own setting, in one place.
- No behaviour change for authenticated endpoints and non-browser clients.

**Non-Goals:**

- Origin rules for the OAuth routes (`/oauth/*`, `.well-known`); they keep the global policy.
- CORS on responses given before the endpoint is resolved (unknown endpoint, parse error, 413). A browser sees those as
  network errors; giving them a grant would need the endpoint before the cheap stages run.
- Changing the admin UI's spec (UI-1) to name the new input; the endpoint page gains a field within what UI-1 already
  describes.

## Decisions

**A domain policy object owns the rule.** `OriginPolicy` (domain, `domain/endpoints/origin_policy.py`) normalises an
entry (lower-case scheme and host, default port dropped, trailing slash dropped; anything with a path, query, fragment
or a non-http(s) scheme is a `ValueError` naming the entry), decides `allows(origin, public_origin)`, and gives
`default_for(auth_modes)`. The DTO validator, the service default, the migration's expectations and the MCP gate all
call it, so the rule is written once. `Endpoint` (domain) gains `allowed_origins: list[str]`.

**The field is optional on write and resolved by the service.** `EndpointUpsert.allowed_origins: list[str] | None`
(validated and normalised through `OriginPolicy`); `EndpointService.upsert` replaces `None` with
`OriginPolicy.default_for(auth_modes)`. `EndpointRead` always carries the resolved list. Bootstrap documents use the
same DTO, so they accept the field with no extra code.

**The gate runs after the endpoint lookup, before authentication.** `AdmissionGate.admit_caller` checks the request's
`Origin` against the loaded endpoint right after `load_bundle_view` and before `authenticate`; a refusal is a
`RequestRejected` with `403` and a JSON-RPC error (`id: null`, `-32600`, "origin not allowed"). The decision travels on
the `EndpointContext` (and on a `RequestRejected` raised after the lookup) as the origin to grant, or none.
`McpGatewayRouter` applies the CORS headers at its single exit, so a 401 challenge, a JSON result and an SSE stream all
get them the same way. *Alternative:* keep CORS in the middleware with a per-replica cache of endpoint origins fed by
invalidation events. It keeps the grant on pre-lookup responses, but adds a second store of endpoint state that must
stay consistent; rejected.

**Preflights get a route.** `McpEndpointController` gains `OPTIONS /{endpoint_name}/mcp`, handled by
`McpGatewayRouter.preflight`: a read of the endpoint by name (no authentication), then either the CORS preflight answer
(the methods and headers SEC-5 lists, `Access-Control-Max-Age: 600` so browsers cache it) or `403` with no CORS headers.
`PathScopedCors` drops its MCP branch and becomes the allow-list policy for every other route.

**Defaults follow the open/closed split.** `[]` for `[none]`, `["*"]` otherwise: authenticated endpoints keep today's
behaviour, and only open endpoints, where cross-site use adds access, change.

**Alembic revision 0011** (infrastructure/postgres) adds `endpoints.allowed_origins` (JSON, not null) and backfills it
row by row from `auth_modes` with the same rule; the downgrade drops the column.

**ADR-0049** records "browser origins are an endpoint setting, not an auth mode", with the alternatives (a new auth
mode; a global origin list; keeping permissive CORS).

## Risks / Trade-offs

- [A browser client of an open endpoint breaks on upgrade] → Called out as breaking in the proposal and the deploy
  guide's upgrade notes; the fix is one list entry. Authenticated endpoints are unchanged.
- [Preflights now read the database] → One lookup by name, as an unauthenticated POST already does; browsers cache the
  answer for ten minutes.
- [Pre-lookup errors are unreadable cross-site] → Documented in the HTTP surface page; non-browser clients and same-site
  pages see them as before.
- [`*` reflects `null`] → Accepted: `*` already means any page, and no credentials are ever granted.

## Migration Plan

Deploy as usual; revision 0011 runs before the new version serves and is readable by the previous release (it only
adds a column). Rolling back: `alembic downgrade 0010`, then the previous image.
