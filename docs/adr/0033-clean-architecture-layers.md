# ADR-0033: Four clean-architecture layers; contracts owned by the application; SQLModel entities as the accepted deviation

**Status:** accepted (amended by [ADR-0034](0034-pydantic-entities-and-row-classes.md): entities are now plain Pydantic
models) · **Date:** 2026-09-08 · **Amends:** [ADR-0003](0003-sqlmodel-pydantic-first.md),
[ADR-0020](0020-library-level-service-layer.md), [ADR-0023](0023-import-contracts-and-shared-providers.md),
[ADR-0025](0025-repository-unit-of-work-and-container.md)

## Context

ADR-0019 through ADR-0027 gave the library a real layering: framework-free services and DTOs, controllers, a method
registry, a repository and unit of work, one typed container. An assessment against Clean Architecture (four layers,
dependencies pointing inward, interfaces owned by the inside) showed the layering was a *stack*, not *rings*.
`services/` sat on `store/`, and `store/` was SQLAlchemy: `Repository[T]` took `ColumnElement` criteria, so every
service wrote SQLAlchemy expressions as its query language (38 constructions, nine direct reaches for `uow.session`),
and every live-store collaborator (`SessionStore`, `RateLimiter`, `SignalBus`, the refresh lock) was injected by its
concrete Redis type. No use case could be tested without SQLAlchemy and fakeredis; eleven of twenty-eight hermetic test
modules booted the whole ASGI app to check one rule. Domain rules lived in the gateway: the ChatGPT re-annotation and
override-merge rules beside a query in `gateway/composition/bundle_view_loader.py`, the health-streak and tool-sync
rules inside a class that also drove FastMCP and a session. And `gateway/` held files from all four layers, `oauth/`
from three, so the ADR-0023 contract proved direction between subsystems, not between layers.

The scanner counted 109 dependency-rule violations; the rubric scored the package 13 of 24. Replacing Postgres or Valkey
would have touched domain, application and api alike.

## Decision drivers

- An interface owned by the caller is the only abstraction that can be faked without the technology it hides; a
  SQLAlchemy convenience is not one.
- Rules that live in the domain can be found by looking in the domain, and tested without a database.
- A contract that names the layers keeps the direction as the code grows; a contract that named subsystems allowed the
  inversion it was written to prevent.
- Grouping adapters by technology makes the swap test answerable: replacing Postgres touches `infrastructure/postgres/`
  and the root.

## Decision

- **Four literal layer packages plus a composition root.** `domain/` (entities grouped by context, value objects, enums,
  `policies/`, the presentation and tool-sync rules; no I/O), `application/` (use cases, `contracts/`, `metering/`,
  `schemas/`, `settings/`, `errors/`; imports domain only), `infrastructure/` (one adapter per contract, grouped by
  technology: `postgres/`, `valkey/`, `fastmcp/`, `httpx/`, `oidc/`, `crypto/`, `egress/`, `metering/`, `readiness/`,
  `inprocess/`, `config/`, and `memory/` fakes), `api/` (`http/` shared machinery; one package per surface —
  `management/`, `health/`, `oauth/`, `mcp/` — each keeping its route classes in a `controllers/` subpackage so a route
  is never mistaken for a helper; `jobs/` for non-HTTP entrypoints) and `main/` (`create_app`, `CompositionRoot`,
  `AppContainer`, `CompositionOverrides`, `McpEdgeAssembly`, the OpenAPI export). The former `services/`, `schemas/`,
  `models/`, `store/`, `crypto/`, `settings/`, `http/`, `providers/`, `gateway/`, `oauth/`, `bootstrap/` and
  `migrations/` packages are dissolved into them; every module kept its name where the name still says what it holds.
- **The interfaces infrastructure fulfils are owned by `application/contracts/`** as `@runtime_checkable` protocols
  whose signatures use domain types only, grouped by subject (`persistence/`, `live_state/`, `upstream/`, `identity/`,
  plus `secret_cipher` and `readiness_probe` at the top). They are called *contracts*, not *ports*: in a network gateway
  "port", "protocol" and "gateway" already name things in the product's own vocabulary, and a package named for the kind
  of object it holds is what the module-naming rule forbids. `MeteringHook`, the one interface third parties implement,
  lives in `application/metering/` beside its context and decision types. `UnitOfWork` exposes one repository accessor
  per entity and no session; each repository contract carries the named queries its use cases need
  (`ApiKeyRepository.by_hash`, `OAuthTokenRepository.revoke_unless_revoked`, `ConsentRepository.active`,
  `AuthorizationCodeRepository.burn`). The SQLAlchemy generic is private to `infrastructure/postgres/` and each adapter
  wraps it in those names. The same holds for the live store (`SessionStore`, `AdminSessionStore`, `SingleUseState`,
  `RateLimiter`, `AuthFailureLimiter`, `SignalBus`, `RefreshLock`), the in-process registry and counters, the audit
  sink, the secret cipher, the readiness probe, the upstream probe and the upstream client factory. Every contract has
  an in-memory implementation under `infrastructure/memory/`; use-case tests run on those.
- **Rules move to the domain.** `PerUserUpstreamPolicy` is a pure decision over entities and `PerUserUpstreamCheck` in
  application loads what it needs; `tool_presentation.present_tool` holds PROF-3 and TM-2/3/4; `tool_sync.sync_tools`
  holds DISC-2/3; the redirect-URI rule raises a domain error the application translates.
- **`Settings` is split.** The value model lives in `application/settings/` so every layer may read it;
  `infrastructure/config/settings.py` holds the `pydantic-settings` loader (`EnvSettings`, `get_settings`).
- **The import contract keys on the layers.** Four contracts: the `layers` order
  `main > api | infrastructure > application > domain` with `api` and `infrastructure` independent; `domain` and
  `application` forbidden every driver (FastAPI, Starlette, redis, httpx, fastmcp, mcp, cryptography, joserfc,
  pydantic-settings, alembic); `api` forbidden `infrastructure`; and `application` forbidden a direct SQLAlchemy or
  SQLModel import.
- **Tests are grouped by layer.** `tests/domain` and `tests/application` need no fixture beyond the memory fakes;
  `tests/infrastructure` uses sqlite and fakeredis per adapter; `tests/api` drives the ASGI app.

Three deviations from the textbook are deliberate:

- **Entities stay SQLModel tables** (ADR-0003). The domain therefore imports SQLAlchemy for its column declarations,
  confined to entity modules and `domain/shared/utc_datetime.py`, and the ORM contract stops at `application/`.
  Splitting sixteen entities into pure classes, row models and mappers would buy a store swap nobody plans and cost a
  mapper per aggregate. If the store ever changes, that split is the migration path.
- **The MCP edge treats `mcp` and `fastmcp` as its protocol framework**, the way the HTTP surfaces treat FastAPI.
  `api/mcp/` speaks JSON-RPC and MCP types directly and drives the upstream client the factory contract hands it; only
  construction of that client (`infrastructure/fastmcp/client_factory.py`) and the discovery probe are adapters.
- **Service classes, not one class per use case.** `ServerService` with six methods on injected contracts is the same
  thing as six use-case classes sharing a constructor; the ADR-0019/0025 shape stays.

## Alternatives considered

- **Pure domain entities with row models and mappers** — the textbook answer to the ORM-in-domain finding; rejected
  because a single mandated store makes the mapper layer (two classes per aggregate) pure cost. Kept as the migration
  path should the store ever change.
- **One class per use case** — `PlaceOrder`-style handlers instead of a service per resource; rejected because the
  existing services already take their contracts through the constructor, so the split would add files without adding a
  seam.
- **Moving the MCP upstream client, relay and call driver into infrastructure behind contracts** — rejected because
  those objects *are* the protocol edge; the upstream client library is the MCP edge's framework the way the web
  framework is the HTTP surfaces', so only client construction and the discovery probe are adapters.
- **Naming the interface package `ports/`** (hexagonal vocabulary) or `interfaces/` — rejected: both collide with words
  the product already uses for network ports, wire protocols and HTTP interfaces, and both name the kind of object
  rather than the subject.
- **`ignore_imports` exceptions in the linter for the ORM-through-entities chain** — forbidden by project rule;
  `allow_indirect_imports` on that one contract states the same intent without an exception list.

## Consequences

- Documentation follows: arc42 §5 shows the layers, the LikeC4 model has a component view of them, CLAUDE.md and the
  `.claude/docs` guidance name the new paths.

### Positive

- All four contracts hold with zero exceptions; the suite passes unchanged in behaviour; use-case tests on fakes run in
  milliseconds.
- `Repository(uow.session, …)` and `uow.session` no longer exist outside `infrastructure/postgres/`.
- Adapters are named for their technology (`ValkeySessionStore`, `SqlAlchemyUnitOfWork`, `QueuedAuditWriter`,
  `FastMcpUpstreamProbe`), so a concrete name in a use case or controller is a visible violation.

### Trade-offs

- Sixteen repository contracts, sixteen adapters and sixteen fakes are more files than one generic repository. Each is
  small and named for its entity.
- `application/contracts/live_state/` holds protocols for in-process objects too (`StreamRegistry`, `Counters`). The
  fake is what the contract buys; it is not a swap.
- The ORM contract needs `allow_indirect_imports`, because entities reach SQLAlchemy by decision; only a direct import
  from application is a violation.

