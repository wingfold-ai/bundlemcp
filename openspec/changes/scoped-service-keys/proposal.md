# Proposal

## Why

A service key opens everything: the whole management API, token introspection and every MCP endpoint that accepts
API keys. The first consumer runs two machine callers that each need one narrow part of that: a bundle sync worker that
reads the configuration and writes bundles and endpoints, and a connector filter on the public MCP paths that only
introspects tokens. With a full service key, a compromise of either, above all of the internet-facing filter, is a
compromise of the gateway.

## What Changes

- A service key may carry `scopes`: `introspect`, `read`, `bundles:write`, `endpoints:write`, `upstreams:write`,
  `keys:manage`, `mcp`. A service key without scopes keeps every right, so existing keys and
  `BUNDLEMCP_INITIAL_SERVICE_KEY` are unchanged. Endpoint keys take none.
- Every management route (`/api/v1/*` and `/metrics`) declares the access it needs: one scope, or full access for
  admins and unscoped keys only. A route without a declaration cannot be built, and a test enumerates every registered
  route. A scoped key outside its scopes gets 403.
- A scoped key without `mcp` never authenticates an MCP call, and introspecting it as a token reports it inactive.
- `keys:manage` acts only on scoped service keys whose scopes the caller holds itself.
- Scopes are set through `POST /api/v1/api-keys` and in the bootstrap document's `api_keys` entries, shown in reads
  and listings, validated against the known set, and offered on the admin app's **API keys** page.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `auth`: adds AUTH-40 (scopes of a service key); modifies AUTH-5 (who may introspect) and AUTH-23 (kinds and scope).
- `management`: adds MGMT-23 (every route declares its access); modifies MGMT-2 (authentication) and MGMT-10 (API
  keys at bootstrap).

## Impact

- **Gateway:** API key entity, schemas and service; the route decorator, `Controller` and `ManagementController`;
  `ManagementAuth`; the introspection route and service; the API-key authenticator of MCP endpoints; the `me` routes;
  the bootstrap key entry and runner.
- **Storage:** migration `0018`, a non-null JSON column `api_keys.scopes` defaulting to `[]` (expand-only).
- **API:** `scopes` on key create and read, the `ApiKeyScope` enum, and an `x-bundlemcp-access` extension on every
  management operation; the web app's generated types follow.
- **Decision:** [ADR-0066](../../../docs/adr/0066-scoped-service-keys.md).
- **Docs:** scopes in `docs/manage/api-keys.md`, `docs/self-hosting/bootstrap.md`, `docs/guide/authentication.md`,
  the glossary, the HTTP surface table and the introspection recipe in `docs/integrate/upstream-identity.md`.
- **Compatibility:** none broken; unscoped service keys keep every right.
- **Resolves:** no GitHub issue.
