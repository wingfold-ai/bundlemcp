# ADR-0019: Thin routers + service layer in the management API

**Status:** accepted · **Date:** 2026-07-03 · **Amended by:** [ADR-0020](0020-library-level-service-layer.md) (the
service + DTO layer moved from `api/` to the library level), [ADR-0026](0026-controllers.md)

## Context

The management-API routers (`packages/bundlemcp/bundlemcp/api/routers/`) had grown logic-heavy: each route handler mixed
HTTP concerns (paths, status codes, auth deps) with the business logic itself — queries, upsert semantics, invariant
checks (UPS-5, BND-14, UPS-30), invalidation publishing, and secret encryption. `schemas.py` was a single 245-line
module holding every DTO, and several DTOs (`UpstreamOAuthConfig`, `UserRead`, `ConsentRead`, `ConfigValue`) were
defined inside router modules. This made the business rules hard to find, hard to test in isolation, and each router
file a mixed-altitude read.

## Decision drivers

- Routers become a readable API surface (route → service call), while invariants like UPS-5/BND-14/UPS-30 live in one
  grep-able place per resource.
- Framework-free services can be unit-tested without an HTTP client and reused by non-HTTP callers (bootstrap, future
  CLI/jobs).
- Central error mapping keeps status-code policy in one file instead of scattered `HTTPException`s.
- One-class-per-file DTO modules keep diffs small and names discoverable; grouping by resource mirrors the
  router/service layout.

## Decision

- **Controller/service split.** Business logic moves to a service layer: `api/services/`, one service class per resource
  file (`ServerService`, `BundleService`, `EndpointService`, `ApiKeyService`, `UserService`, `ConfigService`). Routers
  stay thin: declare the route, apply auth/paging deps, do request-shape checks that are HTTP-contract concerns (e.g.
  `body.name` must match the path), and delegate to exactly one service call.
- **Services are framework-free.** They take an `AsyncSession`/`Redis` (plus collaborators like discovery or the
  upstream token store) via constructor, accept plain values and DTOs, return DTOs, and never import FastAPI. They
  signal failures with domain errors (`api/services/errors/`: `NotFoundError`, `ConflictError`, `InvalidInputError`,
  `PreconditionError`, `UnavailableError`), which a single exception handler in `app.py` maps to HTTP responses
  (404/409/422/400/503) with the same `{"detail": ...}` shape as `HTTPException`.
- **Wiring lives in `deps.py`.** Per-resource provider functions build services from app state and expose them as
  `Annotated` dependencies (`ServerServiceDep`, …), so routers never touch `request.app.state`.
- **DTO package, one class per module.** `api/schemas.py` becomes the `api/schemas/` package, grouped by resource
  context (`servers/`, `tools/`, `bundles/`, `endpoints/`, `api_keys/`, `users/`, `config/`, `common/`) with exactly one
  Pydantic class per module; shared name validation sits in `schemas/validation.py`. `schemas/__init__.py` re-exports
  everything, so `from bundlemcp.api.schemas import X` stays the import path. Router-local DTOs moved into the package.

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

- New resources follow the pattern: DTO modules under `api/schemas/<context>/`, a `<resource>_service.py` with domain
  errors, a thin router, a provider in `deps.py`.
- Raising `HTTPException` from business logic is now a smell; use the domain errors. Status mapping changes happen in
  `app.py`.
- Minor behavior fix along the way: rename endpoints now return 422 (instead of an unhandled 500) when the new name
  fails DTO validation, because the service wraps Pydantic's `ValidationError` into `InvalidInputError`.
- The public HTTP contract is otherwise unchanged; the hermetic suite passes unmodified.

## Addendum (2026-07-05)

The "Wiring lives in `deps.py`" decision above now lives in three specifically-named modules — `api/providers.py`,
`api/auth.py`, and `api/pagination.py` — with the `*Dep` aliases renamed to `*Provider`. See the
[ADR-0020](0020-library-level-service-layer.md) addendum.

> **Superseded in part by [ADR-0023](0023-import-contracts-and-shared-providers.md):** `api/providers.py` is now
> `bundlemcp/providers.py` and `oauth/deps.py` is now `oauth/providers.py`. The layer direction described here is
> enforced by import contracts (`uv run lint-imports`) rather than by grep.
