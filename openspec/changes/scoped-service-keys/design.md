# Design

## Context

See [proposal.md](proposal.md). Today:

- `ManagementController` attaches one `ManagementAuth` dependency to its whole router: an admin session or any
  service key passes, an endpoint key gets 403.
- `IntrospectionAuth` requires `is_service_key`; MCP endpoints accept any active key that reaches the endpoint;
  `MeController` accepts any service key.
- `api_keys.kind` is a string column; keys have no notion of rights beyond their kind.

## Goals / Non-Goals

**Goals:**

- Least privilege for machine callers, with unscoped service keys exactly as today.
- Default deny for scoped keys on every management route, enforced at build time and proven by a test.
- No escalation through `keys:manage`.

**Non-Goals:**

- Roles, per-resource read scopes, or scopes for admin sessions.
- Changing a key's scopes in place.

## Decisions

- **Domain:** `ApiKeyScope` (a `StrEnum`) and `FULL`; `ApiKey.scopes`, `is_scoped`, `grants(access)`,
  `may_introspect` and `calls_endpoints`. `grants` is true for an unscoped service key, true for a scoped one only when
  `access` is one of its scopes and never for `FULL`, and false for endpoint keys.
- **Declaration:** the route decorators take `access=`; `RouteSpec.access` records it; `Controller` publishes it as
  `openapi_extra["x-bundlemcp-access"]` and asks the subclass for per-route dependencies. `ManagementController`
  refuses a route without `access` (`TypeError` at construction) and attaches `ManagementAuth(access)` to each route.
  `MeController` declares `FULL` and refuses scoped keys itself.
- **Scope map:** reads of bundles, endpoints, upstreams, keys and runtime settings are `read`; writes map to the
  resource's `:write` scope; key writes to `keys:manage`; audit, export and import, inspector, logs, users, runtime
  setting writes, metrics and `me` are `FULL` (ADR-0066 lists the reasons).
- **Escalation:** `ApiKeyService.create`, `activate`, `deactivate` and `delete` take the caller's `Principal`, which
  now carries the key's scopes; a scoped caller acts only on service keys with non-empty scopes it holds itself
  (`ForbiddenError`, 403).
- **MCP and introspection:** the API-key authenticator and `IntrospectionService` use `calls_endpoints`;
  `IntrospectionAuth` uses `may_introspect`.
- **Storage:** migration `0018` adds `scopes` as non-null JSON with server default `'[]'`.
- **Route audit test:** walks the app's routes, including routers FastAPI includes lazily, and fails on any `/api/v1`
  or `/metrics` route without a declaration; two further tests call every route with a key lacking its access (403)
  and with a key holding it (not 401 or 403).

## Risks / Trade-offs

- The route audit walks FastAPI's included-router internals (`effective_candidates`); a FastAPI upgrade could change
  them, which the test would show as a failure, not a silent pass (it asserts more than 60 routes).
- Downgrading below `0018` drops the column and turns scoped keys into full keys; the migration says so.
