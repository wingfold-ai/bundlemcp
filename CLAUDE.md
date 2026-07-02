# bundlemcp

> Self-hostable MCP bundling gateway — a focused Python/Nuxt rewrite of the
> bundling core of metamcp.

## Project Overview

bundlemcp registers upstream MCP servers (Streamable HTTP only), composes them
into **bundles**, and exposes each bundle through one or more **endpoints**
shaped for the consuming client (claude.ai OAuth profile, ChatGPT re-annotation
profile, API-key access for scripts). It is designed to be consumed by an
application layer (ultra-mcp adds Keycloak, billing, discovery) but is fully
usable standalone with any OIDC provider.

The `/spec` folder is the source of truth: [spec/README.md](spec/README.md) is
the index, each numbered file is an atomic spec with testable requirement IDs
(`SRV-1`, `EP-3`, …). The decision log in spec/README.md lists deliberately
dropped metamcp features — do not reintroduce them without new evidence.

Architecture rationale lives in `docs/`: arc42 sections in `docs/arc42/`,
MADR-style ADRs in `docs/adr/` (append-only; new architectural decisions land
with an ADR in the same PR), diagrams as LikeC4 models in `docs/likec4/`
(validate with `npx likec4 validate docs/likec4`). Rules: spec 62.

## Architecture

See [spec/00-overview.md](spec/00-overview.md) and
[spec/01-architecture.md](spec/01-architecture.md). Core rules:

- **Stack:** FastAPI + FastMCP v3, SQLModel (Pydantic-native, SQLAlchemy 2.0
  async + asyncpg, Alembic), Redis, Nuxt 4 + Nuxt UI v4. Always adopt the
  latest stable versions.
- **State model:** Postgres = durable config/tokens/audit; Redis = live
  sessions/rate-limits/logs. **No in-memory-only state a request depends on**
  — any replica serves any session; restarts are non-events (spec 30).
- **Pydantic-first:** entities defined once as SQLModel classes; API DTOs are
  Pydantic; frontend TS types are generated from OpenAPI, never hand-written.
- **Layout:** uv workspace — library code in `packages/bundlemcp/` (flat, no
  `src/`), deployable entrypoints in `services/`, Nuxt app in `apps/web/`,
  compose stack in `deploy/`.

## Development

- Python ≥3.13, uv: `uv sync --all-packages`; run services with `uv run`.
- Stack: `docker compose -f deploy/docker-compose.yml up` (gateway, web,
  Postgres, Redis, dev OIDC IdP).
- Sibling read-only reference repos: `../metamcp` (what we're replacing),
  `../ultra-mcp` (first consumer — its registrar and billing contracts drive
  specs 40 and 31).

## Testing

- `uv run pytest -q` — hermetic unit tests (no Docker/network); must pass
  before any change is done. `uv run ruff check .` must be clean.
- Integration tests run against the compose stack; spec 30 mandates
  restart-under-load and two-replica session tests.
- Tests reference spec requirement IDs in their names/docstrings where they
  verify one.

## Conventions

- Ruff (line length 100), full type hints, `pydantic-settings` with
  `BUNDLEMCP_` env prefix.
- Never log or return secrets/tokens/header values (spec 51, DOM-3).
- New behavior starts with a spec update in `/spec`; keep requirement IDs
  stable.

## Git & Commit Attribution

Commits and PRs must land in the user's name, never Claude's. The standing
rules — no `Co-Authored-By: Claude` trailer, no "Generated with Claude Code"
line, commit/PR behavior, and the security guardrails — are documented in:

@.claude/docs/git-attribution.md

Read and follow that file whenever you commit, push, or open a pull request.
