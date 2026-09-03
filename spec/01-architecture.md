# 01 — Architecture

**Status:** Accepted · **Origin:** new (layout follows ultra-mcp conventions)

## Summary

A small, horizontally scalable two-service system: a Python **gateway**
(FastAPI + FastMCP v3) that serves both the MCP endpoints and the management
REST API, and a **Nuxt 4 web app** for administration. Postgres holds all
durable state, Redis holds all live state. Pydantic models are the single
source of truth from database row to frontend type.

## Stack & version policy

| Layer | Choice | Verified latest (2026-07) |
|---|---|---|
| MCP framework | **FastMCP v3** (proxying, composition, middleware) | 3.4.2 |
| HTTP/API | **FastAPI** on uvicorn | — |
| Models/ORM | **SQLModel** (Pydantic-native, on SQLAlchemy 2.0 async + asyncpg) | 0.0.39 |
| Migrations | **Alembic** | — |
| Validation/config | **Pydantic v2** + `pydantic-settings` (`BUNDLEMCP_` env prefix) | 2.13 |
| Live state | **Valkey** (BSD-3, RESP; `redis-py` async client, MIT) | valkey 8 |
| Frontend | **Nuxt 4** + **Nuxt UI v4** (Tailwind v4) | nuxt 4.4.8, @nuxt/ui 4.9.0 |
| Python tooling | **uv** workspace, **ruff**, **pytest** | — |

- **ARC-1** Every framework/tool MUST be adopted at its **latest stable
  version** at the time of implementation, and dependencies MUST specify
  minimum-version pins (`>=`) rather than exact pins for libraries. Staying
  current is a standing rule, not a one-time choice.
- **ARC-2** Python ≥ 3.13 (or latest stable at implementation time), Node ≥ 24
  LTS for the web app.

## Pydantic-first data flow

- **ARC-3** Domain entities MUST be defined **once** as SQLModel classes
  (Pydantic models that are also DB tables). API request/response DTOs MUST be
  Pydantic models (SQLModel table classes or derived read/create/update
  models) — no hand-written duplicate shapes.
- **ARC-4** The gateway MUST publish its OpenAPI schema, and the web app MUST
  generate its TypeScript client types from it (openapi-typescript or hey-api)
  as a build step. Frontend DTOs are **generated, never hand-written**.
- **ARC-5** All tool/endpoint/server inputs MUST be validated by Pydantic at
  the API boundary; validation errors return structured 422 responses.

## Repository layout

uv workspace monorepo, following the `packages/` (importable libraries, flat,
no `src/`) + `apps/` (deployable applications) convention used in
ultra-mcp:

```
bundlemcp/
├── packages/
│   └── bundlemcp/            # the library: all gateway code
│       ├── models/           # SQLModel entities (02-domain-model)
│       ├── gateway/          # FastMCP bundle serving, sessions, middleware
│       ├── oauth/            # OAuth 2.1 server + upstream OAuth client
│       ├── api/              # management API controllers + composition root
│       ├── http/             # Controller base shared by every HTTP surface
│       ├── providers/        # FastAPI providers for shared collaborators
│       ├── services/         # framework-free business logic (any layer consumes)
│       ├── schemas/          # Pydantic DTOs (shared contracts)
│       ├── store/            # Repository + UnitOfWork (Postgres), Redis accessors
│       └── ...
├── apps/
│   ├── gateway/              # main.py composition root + Dockerfile
│   └── web/                  # Nuxt 4 admin UI + its Dockerfile
├── deploy/
│   ├── docker-compose.yml    # gateway, web, postgres, redis, dev IdP
│   └── ...
└── spec/                     # these documents
```

- **ARC-6** All gateway logic lives in `packages/bundlemcp`;
  `apps/gateway` is a thin entrypoint. The web app is self-contained in
  `apps/web`.

## State model (the core architectural rule)

- **ARC-7 (Postgres — durable):** servers, bundles, endpoints, tools cache,
  users, OAuth clients/codes/tokens, upstream OAuth tokens, API keys, audit
  log, config. Postgres is the system of record.
- **ARC-8 (RESP store — live):** MCP session state, upstream session bindings,
  rate-limit counters, live-log ring buffer, cross-replica pub/sub. The store
  never holds configuration; outage behavior is explicitly defined in the
  degradation matrix ([SES-14](30-session-management.md)) — bounded, honest
  degradation, not silent failure. The store is a **RESP-compatible** server —
  the default is **Valkey** (BSD-3), accessed via the MIT `redis-py` client
  ([ADR-0022](../docs/adr/0022-valkey-store.md)); "Redis" elsewhere in these
  specs denotes this RESP store/protocol, not the Redis product specifically.
- **ARC-9** A request MUST be servable by **any gateway replica**: no
  process-local state may be required to route or answer a request
  (details in [30-session-management.md](30-session-management.md)).
- **ARC-10** A gateway restart MUST NOT invalidate client sessions that are
  otherwise still within their lifetime.

## Processes & routing

- **ARC-11** One gateway container serves: `/{endpoint}/mcp` (public MCP,
  [14-endpoints.md](14-endpoints.md)), `/oauth/*` + `/.well-known/*`
  ([20-oauth-server.md](20-oauth-server.md)), `/api/v1/*` (management,
  [40-management-api.md](40-management-api.md)), `/healthz`, `/readyz`,
  `/metrics` ([51-observability.md](51-observability.md)).
- **ARC-12** The web app is a separate container; it talks only to the
  management API. Nothing in the gateway depends on the web app.
- **ARC-13** `deploy/docker-compose.yml` MUST bring up a working stack
  (gateway, web, Postgres, Redis, and a lightweight OIDC IdP for development)
  with a single command; TLS termination is left to the operator's proxy.
  Public base URL, trusted-proxy headers, and cookie attributes are governed
  by [71-deployment.md](71-deployment.md) (DEP-1/DEP-2).
- **ARC-15 (clocks):** time-window logic (rate limits, token expiry) MUST NOT
  assume perfectly synced replica clocks: rate-limit windows use Redis server
  time; token/code expiry tolerates ordinary NTP-level skew (documented
  assumption: replicas run NTP).

## Testing

- **ARC-14** Unit tests are hermetic (no Docker, no network): in-memory/fake
  Redis and SQLite-or-fixture Postgres where feasible. Integration tests run
  against the compose stack. `uv run pytest -q` and `uv run ruff check .` MUST
  be green before any change is done.

## Related documentation

Architecture rationale, views, and decision records live in `docs/arc42/`,
`docs/adr/`, and `docs/likec4/` per
[62-architecture-documentation.md](62-architecture-documentation.md); this
spec stays the normative source for the requirements above.

## Out of scope

- Kubernetes manifests (compose first; k8s can come later) — upgrade/rollout
  rules are in [71-deployment.md](71-deployment.md).
- Multi-region or geo-distribution concerns.

## Open questions

- Whether SQLModel's current release covers all needed SQLAlchemy 2.0 async
  patterns or a thin escape hatch to raw SQLAlchemy models is needed for
  advanced queries (SQLModel classes are SQLAlchemy models, so this is a
  per-case decision, not an architecture change).
