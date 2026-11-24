# ADR-0066: Service keys can be limited to scopes, and every management route declares one

**Status:** accepted · **Date:** 2026-11-24

## Context

A service key was all or nothing: it opened the whole management API (`/api/v1`), token introspection and every MCP
endpoint that accepts API keys. Every component that needed one narrow right held all of them. The first consumer now
runs two such components:

- a **bundle sync worker** that copies ready-made bundles into per-user bundles and needs to read the configuration and
  write bundles and endpoints, nothing else;
- a **connector filter** in front of the gateway's public MCP paths that identifies each caller through introspection.
  It sees every public request, so it is the most exposed component of its deployment; with a service key, its
  compromise would be a compromise of the gateway.

Before the second consumer, a single extra key kind (`introspection`, allowed only to introspect) was considered. It
solves the filter's case and not the worker's, and every further narrow need would add another kind.

## Decision drivers

- Least privilege for machine callers, expressed once and reused for each new need.
- Backward compatible: every existing service key, and `BUNDLEMCP_INITIAL_SERVICE_KEY`, keeps every right.
- Default deny: a management route added later is unreachable by a scoped key until it says what it needs, and a test
  proves no route was left out.
- No escalation: a key that can manage keys never creates or changes a key with more rights than it has.

## Decision

- **Scopes on service keys.** A service key carries an optional list of scopes. An empty list means every right, as
  before. Endpoint keys take none (refused at creation and in the bootstrap file). The scopes are:

  | Scope | Opens |
  |---|---|
  | `introspect` | `POST /oauth/introspect` |
  | `read` | the reads of bundles (members, tools, curation, prompts, resources), endpoints and profiles, upstreams (tools, upstream-OAuth status), API keys, and runtime settings |
  | `bundles:write` | writes to bundles: upsert, rename, delete, members and their order, tool curation, member-prompt and member-resource curation, bundle prompts and bundle resources |
  | `endpoints:write` | endpoint upsert, rename, delete |
  | `upstreams:write` | upstream upsert, rename, delete, `:inspect`, `:from-server-json`, `:refresh-tools`, and upstream-OAuth settings, connect and token deletion |
  | `keys:manage` | API key create, activate, deactivate, delete, only for scoped service keys whose scopes the caller holds itself |
  | `mcp` | authenticating MCP calls on endpoints that accept API keys |

  Names follow `<resource>:<action>` for writes, as OAuth scopes conventionally do, with one-word names where the right
  is not a write. `read` is one scope, not one per resource: the configuration it reveals is the same that the write
  scopes act on, and splitting it would give the worker four scopes for one need.
- **Full-only routes.** Everything else under `/api/v1` and `/metrics` (audit records and their export, configuration
  export and import, the inspector, live logs, users and their consents, changing runtime settings, the `me` routes)
  is open only to admins and unscoped service keys. These either reveal what a caller never needs (logs, audit,
  people) or bypass the other scopes (an import writes every resource kind; the inspector reaches any server).
- **Declared per route, checked per route.** Every management route's decorator names its access (`access=` a scope,
  or `FULL`). A management controller refuses to build a route without one, and the check runs as that route's own
  dependency. The access is published as the `x-bundlemcp-access` OpenAPI extension, and a test walks every registered
  `/api/v1` route and `/metrics` and fails on any without a declaration. A scoped key outside its scopes gets 403.
- **No caller credential without `mcp`.** A scoped key without `mcp` never authenticates an MCP call, and
  introspecting it as a token reports it inactive, so an upstream that admits API-key callers through introspection
  never admits it.
- **Storage.** A JSON column `api_keys.scopes`, non-null with an empty-list default, so existing rows keep every right.

## Alternatives considered

- **An `introspection` key kind.** Smallest change for the connector filter, but it covers one need of the two, and
  each further need would be another kind with its own rules in every authenticator.
- **Scopes per resource and verb for every route** (`bundles:read`, `audit:read`, …). Finer, but no consumer needs it,
  and each new route would have to invent a name. A route that needs more care than the listed scopes give is kept
  full-only instead.
- **Roles (named sets of scopes).** A layer of indirection with nothing to share yet; a role can be added on top of
  scopes later.
- **Deriving the scope from the method** (GET means `read`). It would put configuration export (a GET) and audit and
  log reads into `read` without anyone deciding it; the explicit declaration is the point.

## Consequences

### Positive

- The bundle sync worker runs with `read`, `bundles:write` and `endpoints:write`; the connector filter with `introspect`
  alone. Neither can manage keys, read logs or call tools.
- A new management route cannot ship reachable by scoped keys by accident: it fails to build, and the route audit
  fails, until it declares its access.
- Existing deployments see no change.

### Trade-offs

- Each management route carries one more argument, and changing what a scope opens changes an API contract.
- `keys:manage` limited to the holder's own scopes means a scoped key can never create an endpoint key or a full
  service key; that stays an admin's or a full key's job.
- A scoped key's scopes cannot be changed in place; create a new key and delete the old one.
