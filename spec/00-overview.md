# 00 — Overview

**Status:** Accepted · **Origin:** —

## Vision

bundlemcp does one thing well: **bundle MCP servers and expose the bundles the way each consuming client needs them.**

```
upstream MCP servers ──▶ [ server registry ] ──▶ [ bundle ] ──▶ [ endpoint(s) ]
 (Streamable HTTP)          connection +           tool            per-client
                            tool discovery         curation        surface:
                                                                   auth mode,
                                                                   profile,
                                                                   rate limits
```

A **bundle** aggregates the tools of several upstream servers into one virtual MCP server. An **endpoint** is a public
URL serving that bundle over Streamable HTTP. One bundle can have **many endpoints**, each shaped for its consumer:

- a claude.ai endpoint that requires OAuth 2.1 (dynamic client registration + PKCE),
- a ChatGPT endpoint that re-annotates write tools as read-safe so ChatGPT accepts them,
- an internal endpoint authenticated by API key for scripts and automations.

## Why a rewrite (and not a fork)

metamcp proved the product shape but is barely maintained (the author has said development will stay slow) and has an
architectural flaw that caused repeated production pain:
**all live state — connection pools, transports, rate-limit counters — lives in the memory of a single Node process.** A
restart drops every session (`404 Session not found` storms); a second replica is impossible; the fork accumulated an
entire recovery subsystem (`session-error.ts`, invalidate-and-retry, re-init-on-404) just to mitigate it.

bundlemcp inverts that: durable configuration in Postgres, live session state in Redis,
**no in-memory-only state that a request depends on**. Any replica serves any session; restarts are non-events. See
[30-session-management.md](30-session-management.md).

The rewrite also switches to the maintainer's home stack — Python (FastAPI + FastMCP v4, Pydantic everywhere) and Nuxt 4
— and strips features that don't serve the bundling mission (see the decision log in
[README.md](README.md)).

## Scope boundary: bundlemcp vs. the application layer

bundlemcp is the **reusable building block**; the application layer is an **application** of it (a commercial
multi-tenant MCP platform). bundlemcp must be fully usable standalone — with any OIDC provider and no billing — while
exposing the exact contact points such an application needs.

| Concern | bundlemcp (this project) | Application layer |
|---|---|---|
| MCP aggregation, bundles, endpoints | ✔ owns | consumes |
| OAuth 2.1 server toward MCP clients (+ token introspection) | ✔ owns | consumes `sub` for billing |
| Admin authentication | federates to **an external OIDC IdP** | ships and operates Keycloak |
| Server registration | ✔ management REST API | registrar (Docker-label discovery) calls it |
| Tool-call interception | ✔ middleware chain + documented metering hook | plugs check-and-debit / refund into the hook |
| Identity propagation to upstreams | ✔ header forwarding + `X-MCP-User` | upstream servers rely on it |
| Billing, credits, Stripe, pricing | ✖ never | ✔ owns |
| Identity provider itself | ✖ required but external | ✔ owns (Keycloak realms) |
| Container discovery | ✖ | ✔ owns (label contract) |
| Storefront | ✖ | ✔ owns |

The two integration warts this boundary explicitly fixes:

1. metamcp had **no service-authenticated registration API** — the first consumer's registrar had to replay better-auth
   login cookies against internal tRPC. bundlemcp ships a first-class REST API
   ([40-management-api.md](40-management-api.md)).
2. metamcp's metering middleware was a code comment ("Add more middleware here as needed"). bundlemcp specs the hook as
   a supported contract ([31-middleware.md](31-middleware.md)) matching the first consumer's existing `check-and-debit`
   / `refund` API.

## Goals

1. Bundle Streamable-HTTP MCP servers and serve bundles over Streamable HTTP.
2. Per-client endpoint shaping (auth mode, tool re-annotation, rate limits).
3. Survive restarts and scale horizontally without losing sessions.
4. Everything manageable via UI **and** an equivalent authenticated REST API.
5. Pydantic-typed end to end: DB model → API DTO → generated TS types in the UI.
6. Deployable as a small Docker Compose stack: gateway, web, Postgres, Valkey (+ any OIDC IdP).

## Non-goals

- Being an MCP server marketplace, an IdP, or a billing system.
- Supporting every MCP transport ever shipped (Streamable HTTP only).
- Multi-tenancy inside bundlemcp (single shared admin workspace).
