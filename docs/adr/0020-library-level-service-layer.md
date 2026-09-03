# ADR-0020: Service + DTO layer at the library level; `apps/` for deployables

**Status:** accepted · **Date:** 2026-07-04 · **Amends:** [ADR-0019](0019-api-service-layer.md)

## Context

ADR-0019 introduced a controller/service split but placed the layer under
`packages/bundlemcp/bundlemcp/api/services/` (and the DTOs under
`api/schemas/`). That location contradicted its own rationale — "reused by
non-HTTP callers (bootstrap, future CLI/jobs)" — and the contradiction was
already load-bearing: `bootstrap.py` reimplemented the server/bundle/endpoint
upserts inline rather than import "down" from `api/`, and it pulled DTOs from
`bundlemcp.api.schemas`. Extracting the authentication logic still living in
`api/deps.py` (the API-key lookup with its KEY-4 last-used write, and the
admin-session DB re-validation) made the inversion concrete: the MCP edge
(`gateway/`) and the OAuth token endpoint (`oauth/`) already imported
`resolve_api_key` from `bundlemcp.api.deps`, so `api/` owned a dependency of its
own peers.

A second, smaller problem: the workspace root used `services/` for **deployable
composition roots** (`services/gateway/`), colliding with the natural name for
the business-logic layer.

## Decision

- **The service and DTO layers move to the library level:** `api/services/` →
  `bundlemcp/services/`, `api/schemas/` → `bundlemcp/schemas/`. They are peers
  of `models/` and `store/`, consumed by `api/`, `gateway/`, `oauth/`,
  `bootstrap`, and any future CLI as equals. `api/` is now just one consumer —
  routers plus the FastAPI wiring in `deps.py`.
- **The layers never import `api/` or FastAPI.** `api/validators.py` (only
  `models` + SQLAlchemy) moved to `bundlemcp/validators.py` to remove the last
  back-edge from a service into `api/`. Enforced by grep in the verify step.
- **`AuthService` (in `bundlemcp/services/`) is framework-free.** It takes
  header/cookie strings and an `AsyncSession`, never a web `Request`, so all
  three edges reuse it. HTTP status policy (401 vs 403) and the CSRF origin
  check stay at each edge; `api/deps.py` keeps them. Key extraction is a
  static `AuthService.extract_key(authorization, x_api_key)`. `Principal` is
  co-located with `AuthService` (it is an auth domain type, not a serialized
  Pydantic DTO, so it stays out of the Pydantic `schemas/` package).
- **`bootstrap` consumes the services** instead of duplicating their upserts,
  making the ADR-0019 reuse promise real and inheriting every invariant
  (SRV-*, UPO-6, PROF-6) and correct `rate_limit` serialization.
- **Workspace convention: `apps/` = deployable applications, `packages/` =
  libraries.** Root `services/` → `apps/`, so the deployable gateway is
  `apps/gateway/` beside the planned `apps/web/`, freeing `services/` for the
  library layer. Gateway is not a uv workspace member, so `uv.lock` is
  unaffected.

## Reasons

- Ownership follows consumption: a layer used by four subsystems belongs to
  none of them in particular — it belongs to the library.
- A framework-free `AuthService` is unit-testable without an HTTP client and
  removes the `gateway → api` and `oauth → api` edges.
- The `apps/`/`packages/` split is the conventional monorepo layout and ends
  the `services/` name overload cleanly.

## Consequences

- (+) No subsystem imports `bundlemcp.api` except `api/` itself; `services/`
  and `schemas/` import neither FastAPI nor `bundlemcp.api` (grep-verified).
- (+) `bootstrap` and the management API now share one code path, so seeds and
  API calls enforce identical invariants.
- (+) Import moves are mechanical and behavior-preserving; the hermetic suite
  passes unchanged at every step.
- (−) HTTP 401/403 for management auth stays outside the service-layer domain
  errors (no 401/403 in the `ServiceError` → status map); this is correct —
  the accept-either status decision is an HTTP-contract concern the edge owns.
- New resources follow ADR-0019's pattern, but the files land under
  `bundlemcp/services/` and `bundlemcp/schemas/`, not `api/`.

## Addendum (2026-07-05)

`api/deps.py` was subsequently split into three specifically-named modules
within `api/`:

- **`api/providers.py`** — the generic DI glue: `get_db`/`get_redis` and the six
  `get_*_service` functions.
- **`api/auth.py`** — the management-auth edge as a `ManagementAuth` class
  (CSRF origin check + accept-either 401/403 policy), plus `get_auth_service`,
  `AuthServiceProvider`, and `ServiceAuthProvider`.
- **`api/pagination.py`** — `Pagination` + `PageProvider`.

The `Annotated[T, Depends(...)]` aliases were renamed from `*Dep` to `*Provider`
(`DbDep` → `DbProvider`, `ServiceAuthDep` → `ServiceAuthProvider`, …): "provider"
reads as app-owned glue that yields a value, whereas "dependency" implies
something external. So references above to "the FastAPI wiring in `deps.py`" now
mean these three files. Behavior is unchanged — pure code motion, one
function→class rewrite, and a mechanical rename.

> **Superseded in part by [ADR-0023](0023-import-contracts-and-shared-providers.md):**
> `api/providers.py` is now `bundlemcp/providers.py` and `oauth/deps.py` is now
> `oauth/providers.py`. The layer direction described here is enforced by
> import contracts (`uv run lint-imports`) rather than by grep.
