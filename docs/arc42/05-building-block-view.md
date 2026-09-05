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

## Level 2 — gateway internals (planned package layout, ARC-6)

```
packages/bundlemcp/
├── models/     # SQLModel entities (spec 02)
├── schemas/    # Pydantic DTOs — shared contracts (ADR-0020)
├── services/   # framework-free business logic incl. AuthService (ADR-0019/0020)
├── gateway/    # endpoint serving, bundle composition, sessions,
│               # protocol relay, middleware chain (specs 12–16, 30–33)
├── oauth/      # OAuth 2.1 server + upstream OAuth client (specs 20, 23)
├── http/       # the Controller base every HTTP surface is declared with (ADR-0026)
├── providers/  # FastAPI providers for shared collaborators (ADR-0023)
├── api/        # management API controllers + the composition root (spec 40)
└── store/      # Repository, UnitOfWork, session/admin-session stores, Redis accessors
```

`services/` and `schemas/` sit below `api/`/`gateway/`/`oauth/`: they import
neither FastAPI nor `bundlemcp.api`, so every subsystem (and `bootstrap`)
consumes them as peers — `api/` is one HTTP consumer, not their owner
(ADR-0020).

Key internal seams:

- **Middleware chain** ([spec/31](../../spec/31-middleware.md)): filter →
  overrides → profile → metering hook → audit; the hook is the only
  sanctioned third-party extension point.
- **Egress layer** ([SEC-1](../../spec/70-security.md)): all
  gateway-initiated HTTP to admin-supplied URLs passes one policy module.
- **Session store** ([spec/30](../../spec/30-session-management.md)):
  the only component allowed to touch session records; enforces atomic
  updates (SES-1a).
