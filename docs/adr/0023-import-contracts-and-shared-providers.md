# ADR-0023: Enforce layer direction with import contracts; every library-level module is a package

**Status:** accepted · **Date:** 2026-09-03 · **Amends:** [ADR-0020](0020-library-level-service-layer.md)

## Context

ADR-0019 and ADR-0020 established the layering this library depends on:
business logic and DTOs are framework-free, and `api/`, `gateway/`, `oauth/`
and `bootstrap` consume them as peers. ADR-0020 recorded the outcome as "no
subsystem imports `bundlemcp.api` except `api/` itself; `services/` and
`schemas/` import neither FastAPI nor `bundlemcp.api` (grep-verified)."

Grep verification is a one-time act, not a standing guarantee. Building the
actual import graph showed the framework-free half had held perfectly — zero
FastAPI imports below the delivery layer — while the direction half had
regressed in two places:

- **Six OAuth route modules imported `api/providers.py`** (`metadata`,
  `registration`, `authorize`, `token`, `upstream_connect`, `oidc/routes`), so
  `api/` again owned a dependency of its own peer. This is the same inversion
  ADR-0020 removed for `resolve_api_key`, reintroduced through the DI glue that
  its own addendum created.
- **`services/config_service` imported `gateway/runtime_config`** for
  `DEFAULTS`, `coerce` and `UnknownConfigKey`, putting a service below-layer
  module in the position of reaching upward.

Neither was real coupling. Both were misfiled modules: the sibling
`oauth/deps.py` already described `api/providers.py` in its own docstring as
"the shared provider module", and the runtime-config registry is framework-free
domain knowledge that happened to sit beside the gateway's per-replica cache.

## Decision

- **Adopt `import-linter` (`uv run lint-imports`), run in CI beside Ruff.** Two
  contracts: a `forbidden` contract keeping `services`, `schemas` and `models`
  free of `fastapi`/`starlette`, and a `layers` contract fixing the direction:

  ```
  api → bootstrap → (gateway : oauth) → providers → services → schemas
      → (models : store : crypto) → settings
  ```

  `gateway : oauth` marks them siblings that may import each other, which is
  what they genuinely are — the edge needs upstream token handling and the
  OAuth routes need edge internals. `exclude_type_checking_imports` is on:
  a `TYPE_CHECKING` import creates no runtime coupling, so annotating an
  injected collaborator's type is not a violation.

- **`api/providers.py` moves to `bundlemcp/providers.py`.** It is consumed by
  both the management-API routers and the OAuth routes, so under ADR-0020's own
  rule — ownership follows consumption — it belongs to neither and therefore to
  the library. It joins `settings.py`, `security.py` and `validators.py` as a
  top-level cross-cutting module.

- **`oauth/deps.py` becomes `oauth/providers.py`**, establishing one convention:
  *a package that owns collaborators exposes them from its own `providers`
  module; providers no single package owns live in `bundlemcp/providers.py`.*
  `AuthFailureLimiterProvider` moves into it, since the token endpoint is its
  only consumer and it was the sole reason the shared module imported
  `gateway/`.

- **The runtime-config key registry moves down.** `DEFAULTS`, `coerce` and
  `UnknownConfigKey` become `bundlemcp/services/config_service/` (a package,
  following `services/auth_service/`), beside the service that owns config
  semantics. `gateway/runtime_config` keeps `RuntimeConfig` — the per-replica
  cache, which is genuinely gateway machinery — and imports the registry
  downward, re-exporting it for gateway-side consumers.

- **Every library-level module becomes a package; nothing sits loose beside
  them.** The package root previously mixed ten packages with four modules
  (`settings.py`, `security.py`, `validators.py`, `providers.py`), which read as
  "these four fit nowhere". Two of them had a home:

  - `security.py` → `crypto/tokens.py`. Both are cryptographic handling of
    secrets — `tokens` is the one-way half (generate, hash, constant-time
    compare), the existing cipher the reversible half.
  - `validators.py` → `services/validators.py`. Framework-free cross-resource
    invariants over `models`, consumed only by `endpoint_service`.

  The other two became packages in the shape the rest of the library already
  uses (`crypto/`, `services/auth_service/`): a class per module plus a
  `_functions.py`, re-exported from `__init__.py`. `settings/` splits into the
  `Settings` model and the cached `get_settings` accessor.

- **No `ignore_imports` entries.** A whitelist of known violations is a to-do
  list, not a contract; both contracts pass with zero exceptions.

## Reasons

- An architectural rule that only review enforces decays silently between
  reviews. Both regressions here landed under an ADR that forbade them.
- The fixes are relocations, not redesigns: every edge removed was a module in
  the wrong package, which is why the change is behavior-preserving.
- Encoding the layer order makes it legible. The contract is now the shortest
  accurate statement of how this library is arranged.

## Consequences

- (+) `services`/`schemas`/`models` are mechanically framework-free, and the
  `oauth → api` edge cannot silently return.
- (+) One statable rule for where a provider lives, replacing case-by-case
  judgement.
- (+) The package root is now uniform — every entry is a package, and the
  contract names all of them, so the layer list doubles as the map of the
  library.
- (+) Pure code motion: the hermetic suite passes unchanged (154 tests).
- (−) A genuine new cross-layer import now fails CI rather than review. That is
  the point, but it means an intentional layering change must update the
  contract in the same commit — which is the ADR trigger anyway.
- The `gateway : oauth` sibling pair is recorded as accepted, not as debt. If
  the mutual dependency is ever broken they become ordered layers.
