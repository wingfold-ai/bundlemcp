# Proposal

## Why

SEC-5, shipped with `harden-http-edge` (#121), makes every MCP endpoint reflect any `Origin` without credentials, so
browser-based MCP clients work from any site. For endpoints that require a credential that adds no access: a page can
only present tokens it already holds. For an open endpoint (`auth_modes: [none]`) it does: a website a visitor opens
can drive the visitor's browser against an endpoint the visitor can reach and the website cannot, such as a gateway
on a company network, and read the answers. That is the DNS-rebinding and cross-site case the MCP Streamable HTTP
transport asks servers to defend against by validating `Origin`. An origin check is a browser policy, not
authentication (any non-browser client sends whatever `Origin` it likes), so it is modelled as an endpoint setting
beside the auth modes, not as an auth mode.

## What Changes

- Each endpoint gets **`allowed_origins`**: the browser origins that may use `/{endpoint}/mcp` across sites. An entry is
  an origin (`https://app.example`, scheme and host with an optional port) or the single wildcard `*` for any origin.
- A request whose `Origin` is the gateway's own public origin, or is on the list, is served and gets CORS for that
  origin (reflected, never credentials, `Mcp-Session-Id` and `WWW-Authenticate` exposed), as SEC-5 does today.
- A request carrying any other `Origin` is refused with **403** and a JSON-RPC error, after the endpoint is looked up
  and before any authentication. A preflight from such an origin gets 403 without CORS headers.
- A request without `Origin` (curl, scripts, agents, servers) is not affected and goes through `auth_modes` as before.
- **Defaults:** an endpoint whose `auth_modes` is `[none]` gets `[]` (no cross-site browser use); every other endpoint
  gets `["*"]`, which is today's behaviour. An upsert that omits the field gets the default for its auth modes, the
  same full-replace rule the other endpoint fields follow. A migration sets existing rows the same way.
- **BREAKING** (narrowly): a browser client on another origin that uses an open (`none`) endpoint stops working until
  its origin is listed. Non-browser clients and every authenticated endpoint are unaffected.
- The management API, bootstrap documents and the endpoint page in the admin UI read and write the field.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `endpoints`: adds EP-24 (allowed browser origins: the field, its validation and defaults, and the 403).
- `security`: SEC-5 (MCP endpoint CORS follows the endpoint's allowed origins instead of reflecting every origin).

## Impact

- **Code:** the endpoint entity, row and repository mapping; `EndpointUpsert`/`EndpointRead`; the endpoint service's
  defaulting; the MCP edge (an origin gate after the endpoint lookup, CORS headers on its responses, an `OPTIONS`
  route); the path-scoped CORS middleware loses its MCP branch; the endpoint page in `apps/web`.
- **Database:** Alembic revision `0011` adds `endpoints.allowed_origins` (JSON list) and backfills it.
- **API:** a new field on the endpoint DTOs; `apps/web/openapi.json` and `types/api.d.ts` regenerate.
- **Docs:** `docs/integrate/http-surface.md` (CORS), `docs/manage/endpoints.md` (the field), `docs/self-hosting/
  bootstrap.md`, `docs/connect/` where browser clients are mentioned.
- **ADR:** ADR-0049, "Browser origins are an endpoint setting, not an auth mode".
- **Depends on** `harden-http-edge` (#121), which added SEC-5; this change is stacked on it.
- No GitHub issue; follow-up from the review of #121.
