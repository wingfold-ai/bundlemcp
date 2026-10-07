# bundlemcp

> Self-hostable MCP bundling gateway — a focused Python/Nuxt rewrite of the bundling core of metamcp.

## Project Overview

bundlemcp registers upstream MCP servers (Streamable HTTP only), composes them into **bundles**, and exposes each bundle
through one or more **endpoints** shaped for the consuming client (claude.ai OAuth profile, ChatGPT re-annotation
profile, API-key access for scripts). It is designed to be consumed by an application layer that adds Keycloak, billing
and discovery, but is fully usable standalone with any OIDC provider.

The `/spec` folder is the source of truth: [spec/README.md](spec/README.md) is the index, each numbered file is an
atomic spec with testable requirement IDs (`SRV-1`, `EP-3`, …). The decision log in spec/README.md lists deliberately
dropped metamcp features — do not reintroduce them without new evidence.

Architecture rationale lives in `docs/`: arc42 sections in `docs/arc42/`, MADR-style ADRs in `docs/adr/` (append-only;
new architectural decisions land with an ADR in the same PR), diagrams as LikeC4 models in `docs/likec4/` (validate with
`npx likec4 validate docs/likec4`). Rules: spec 62.

## Architecture

See [spec/00-overview.md](spec/00-overview.md) and [spec/01-architecture.md](spec/01-architecture.md). Core rules:

- **Stack:** FastAPI + FastMCP v4, SQLModel (Pydantic-native, SQLAlchemy 2.0 async + asyncpg, Alembic), Valkey (BSD-3,
  RESP; via the MIT redis-py client — ADR-0022), Nuxt 4 + Nuxt UI v4. Always adopt the latest stable versions.
- **State model:** Postgres = durable config/tokens/audit; Valkey (RESP) = live sessions/rate-limits/logs.
  **No in-memory-only state a request depends on** — any replica serves any session; restarts are non-events (spec 30).
- **Pydantic-first:** entities are plain Pydantic models in `domain/`; their tables are SQLModel row classes in
  `infrastructure/postgres/rows/`, mapped by the repositories (ADR-0034); API DTOs are Pydantic; frontend TS types are
  generated from OpenAPI, never hand-written.
- **Layout:** uv workspace — library code in `packages/bundlemcp/` (flat, no `src/`), deployable applications in `apps/`
  (gateway entrypoint, Nuxt `apps/web`), compose stack in `deploy/`. The library is four clean-architecture layers plus
  a composition root (ADR-0033): `domain/` (entities, value objects, rules; plain Pydantic, no I/O), `application/` (use
  cases, `contracts/` — the interfaces infrastructure fulfils, grouped by subject — `metering/`, `schemas/` DTOs,
  `settings/`; imports domain only), `infrastructure/` (one adapter per contract, grouped by technology: `postgres/`,
  `valkey/`, `fastmcp/`, `httpx/`, `memory/` fakes, …), `api/` (FastAPI controllers for `/api/v1`, OAuth and the MCP
  edge; names contracts, never adapters) and `main/` (the only place adapters meet use cases). Every HTTP surface is a
  `Controller` subclass (ADR-0026); services take a `UnitOfWork` contract whose repositories are contracts too
  (ADR-0025/0033).

## Development

- Python ≥3.13, uv: `uv sync --all-packages`; run services with `uv run`.
- Stack: `docker compose -f deploy/docker-compose.yml up` (gateway, web, Postgres, Valkey, dev OIDC IdP).
- Sibling read-only reference repo: `../metamcp` (what we're replacing). The first consumer, a private application
  layer, is never named in this repo; its registrar and billing contracts drive specs 40 and 31.

## Testing

- `uv run pytest -q` — hermetic tests (no Docker/network) grouped by layer: `tests/domain` and `tests/application` run
  on pure objects and the `infrastructure/memory` fakes, `tests/infrastructure` on sqlite and fakeredis, `tests/api`
  through the ASGI app. Must pass before any change is done. `uv run ruff check .` must be clean, and so must
  `uv run rumdl check .` (Markdown lines stay within 120 columns; `uv run rumdl fmt .` rewraps longer ones).
- `uv run lint-imports` — import contracts (ADR-0023/0033): the inward layer direction, `domain/` and `application/`
  free of every driver, `api/` never naming an adapter, `application/` never touching the ORM. Must pass with zero
  exceptions; never silence a violation with `ignore_imports`. Delete `.import_linter_cache` after moving modules; a
  stale cache reports kept contracts that are broken.
- Integration tests run against the compose stack; spec 30 mandates restart-under-load and two-replica session tests.
- Tests reference spec requirement IDs in their names/docstrings where they verify one.

## Conventions

- Ruff (line length 100), full type hints, `pydantic-settings` with `BUNDLEMCP_` env prefix.
- Docstrings never reference spec numbers or requirement IDs — they must explain the behavior standalone, or be omitted.
  Requirement-ID cross-references belong in inline `#` comments, test names/docstrings, and error messages only.
- Never log or return secrets/tokens/header values (spec 51, DOM-3).
- **Pydantic everywhere, no `dataclasses`.** Every structured value is a `BaseModel` (SQLModel for the row classes);
  `X | None` only where `None` is really reachable. The config recipes, the `@runtime_checkable` rule for `Protocol`
  fields, and the boundary round-trip pattern are in:

@.claude/docs/pydantic-models.md

- Every model field carries a `description`; on `schemas/` DTOs and `Settings` it is published API surface (OpenAPI, the
  generated TS client, operators), so write those for a reader without the source. Constraints and defaults belong in
  `Field`, requirement IDs stay in `#` comments:

@.claude/docs/pydantic-fields.md

- **No `_common.py` / `_functions.py` / `utils.py`.** A module is named for what it holds, not for the kind of object
  inside it; one function is enough to justify one file. Where a constant, factory or logger belongs instead is in:

@.claude/docs/module-naming.md

- **Design principles and intrinsic naming.** Protocols and modules are named for their inherent architectural mechanism
  (no temporal labels like `modern` or `legacy`), DoS defense sequences cheap in-memory checks before DB I/O, and
  differing transport capabilities are modeled with Front Controller + Protocol Adapters:

@.claude/docs/design-principles.md

- **Controllers, not route functions.** An HTTP surface is a class deriving from `Controller`; its shared policy is a
  router-level dependency; handlers call one service method. The MCP edge dispatches JSON-RPC through a `MethodRegistry`
  of handler classes, never an `if method ==` chain. Rules, and how a new resource or method is added, are in:

@.claude/docs/controllers.md

- **Value objects and entity behavior.** Nothing crosses a layer as a tuple or an untyped dict; a fact about an entity
  (`server.requires_per_user_token`, `token.is_usable`) is a property on the entity, written once. Services take a
  `UnitOfWork` and query through `Repository[T]`; invariants that span resources are policy objects
  (`PerUserUpstreamPolicy`). See ADR-0024/0025.
- New behavior starts with a spec update in `/spec`; keep requirement IDs stable.
- Local aliases (`state = self._app.state`) must add meaning, not save typing — the rules, and the cases that justify
  one, are in:

@.claude/docs/local-aliasing.md

## Git & Commit Attribution

Commits and PRs must land in the user's name, never Claude's. The standing rules — no `Co-Authored-By: Claude` trailer,
no "Generated with Claude Code" line, commit/PR behavior, and the security guardrails — are documented in:

@.claude/docs/git-attribution.md

Read and follow that file whenever you commit, push, or open a pull request.
