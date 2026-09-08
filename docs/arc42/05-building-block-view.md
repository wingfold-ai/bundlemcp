# 5. Building Block View

## Level 1 — containers

LikeC4 view `containers` in [`../likec4/model.c4`](../likec4/model.c4):

```likec4-view
view: containers — "bundlemcp — Containers"
```

| Block | Responsibility | Spec |
|---|---|---|
| **Gateway** (FastAPI + FastMCP v4) | Bundle endpoints (bidirectional MCP proxy), OAuth 2.1 server, management REST API, middleware/metering, bootstrap | 10–33, 40–42 |
| **Admin Web App** (Nuxt 4) | Management UI; pure client of `/api/v1` with generated types | [60](../../spec/60-admin-ui.md) |
| **Postgres** | Durable: config, users, tokens, tool cache, audit | [02](../../spec/02-domain-model.md) |
| **Redis** | Live: sessions, bindings, rate limits, log ring, pub/sub | [30](../../spec/30-session-management.md), [33](../../spec/33-state-propagation.md) |

## Level 2 — gateway layers (ARC-6, ADR-0033)

LikeC4 view `layers` in [`../likec4/model.c4`](../likec4/model.c4):

```likec4-view
view: layers — "Gateway — Clean-architecture layers"
```

The library `packages/bundlemcp/bundlemcp/` is four layers and a composition
root. Dependencies point inward: `api` and `infrastructure` import
`application`, `application` imports `domain`, and no layer knows the one
outside it. `uv run lint-imports` enforces the direction and keeps the inner
two layers free of every driver.

```
packages/bundlemcp/bundlemcp/
├── domain/          entities by context (servers, bundles, endpoints, access,
│                    oauth, upstream_oauth, audit, config, sessions), value
│                    objects, enums, policies/; plain Pydantic, no I/O
├── application/     use cases (management/, auth/, oauth_server/,
│                    upstream_oauth/, discovery/, serving/, bootstrap/),
│                    contracts/ (persistence, live_state, upstream, identity),
│                    metering/, schemas/ (DTOs), settings/, errors/
├── infrastructure/  adapters by technology: postgres/ (rows/, repositories,
│                    unit of work, migrations), valkey/, fastmcp/,
│                    httpx/, oidc/, crypto/, egress/, metering/, readiness/,
│                    inprocess/, config/, memory/ (fakes)
├── api/             http/ (Controller base, providers); one package per surface,
│                    each with controllers/: management/ (/api/v1), health/,
│                    oauth/ (OAuth 2.1 server, login, upstream connect; plus
│                    pages/, browser_state/), mcp/ (the Streamable-HTTP MCP
│                    edge); jobs/ (scheduled entrypoints)
└── main/            create_app, CompositionRoot, AppContainer, overrides
```

| Layer | Holds | Imports | Black-box contract |
|---|---|---|---|
| **domain** | Pydantic entities with their behaviour (`McpServer.requires_per_user_token`, `OAuthAccessToken.is_usable`), value objects (`CallerIdentity`, `PresentedName`, `SessionRecord`), enums, pure rules (`PerUserUpstreamPolicy`, `present_tool`, `sync_tools`) | stdlib and pydantic only (ADR-0034) | Answers every question about an entity from the entity |
| **application** | One service per resource or flow, taking a `UnitOfWork` and the contracts it needs; `contracts/` (the interfaces infrastructure must fulfil, grouped by subject: persistence, live state, upstream servers, identity) and `metering/` (the billing extension point); `schemas/` DTOs that become the OpenAPI document; `settings/` | domain | Every use case runs on the `infrastructure/memory` fakes |
| **infrastructure** | `SqlAlchemyUnitOfWork`, one `SqlAlchemy*Repository` per contract mapping the `rows/` table classes to entities; `Valkey*` stores, limiters, signal bus, invalidation; `FastMcpUpstreamProbe` and the client factory; `HttpxUpstreamProvider`, `JoseOidcProvider`; `TokenCipher`; the egress policy; `InMemory*` fakes | application, domain, drivers | Replacing a store touches one technology folder and `main/` |
| **api** | `Controller` base and providers, the `/api/v1` controllers, the OAuth controllers, `McpEdge` with its method handlers, dialects, relay and tool-call pipeline | application, domain, FastAPI; `api/mcp` also the MCP protocol library | Parse → DTO → one service call → response; names contracts, never adapters |
| **main** | `CompositionRoot` acquires adapters in order and publishes one typed `AppContainer`; `CompositionOverrides` names the seams a test substitutes | everything | The only module that names an adapter beside a use case |

Key internal seams:

- **Middleware chain** ([spec/31](../../spec/31-middleware.md)): filter →
  overrides → profile → metering hook → audit; the hook is the only
  sanctioned third-party extension point (`application/metering/metering_hook.py`).
- **Egress layer** ([SEC-1](../../spec/70-security.md)): all
  gateway-initiated HTTP to admin-supplied URLs passes one policy module
  (`infrastructure/egress/egress_policy.py`).
- **Session store** ([spec/30](../../spec/30-session-management.md)):
  the only component allowed to touch session records; enforces atomic
  updates (SES-1a) (`infrastructure/valkey/session_store.py` behind the
  `SessionStore` contract).
