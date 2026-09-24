# bundlemcp — Specifications

bundlemcp is a self-hostable **MCP bundling gateway**: register upstream MCP
servers, compose them into **bundles**, and expose each bundle through one or
more **endpoints** tailored to the consuming client (claude.ai, ChatGPT, plain
API clients). It is a focused Python/Nuxt rewrite of the bundling core of
[metamcp](https://github.com/metatool-ai/metamcp), designed from day one for
restart-safe sessions and horizontal scaling, and built to be consumed by an
application layer that adds its own identity provider, billing, and discovery
on top.

## How to read these specs

Every numbered file is an **atomic spec**: one capability, independently
acceptable. Shared structure:

| Section | Meaning |
|---|---|
| **Status** | `Accepted` (agreed scope) / `Draft` (open) |
| **Origin** | `metamcp carry-over`, `improvement` (carried over but redesigned), or `new` |
| **Summary** | What and why, in a paragraph |
| **Requirements** | Numbered, testable MUST/SHOULD statements (`SRV-1`, `EP-3`, …) — implementation tasks and tests reference these IDs |
| **Out of scope** | Explicit non-goals of this spec |
| **Open questions** | Deferred decisions, resolved during implementation |

## Index

### Foundation
| Spec | Contents |
|---|---|
| [00-overview.md](00-overview.md) | Vision, scope, boundary with the application layer |
| [01-architecture.md](01-architecture.md) | Stack, version policy, repo layout, state model, Pydantic-first data flow |
| [02-domain-model.md](02-domain-model.md) | Entities and relationships |

### Bundling core
| Spec | Contents |
|---|---|
| [10-server-registry.md](10-server-registry.md) | Upstream MCP server CRUD (Streamable HTTP only), per-server protocol era |
| [11-tool-discovery.md](11-tool-discovery.md) | Tool discovery and Postgres cache |
| [12-bundles.md](12-bundles.md) | Bundle composition, tool prefixing, collisions |
| [13-tool-management.md](13-tool-management.md) | Per-bundle tool enable/disable + overrides |
| [14-endpoints.md](14-endpoints.md) | Public endpoints, N per bundle, auth modes, one URL for every protocol era |
| [15-endpoint-profiles.md](15-endpoint-profiles.md) | claude.ai / chatgpt / default profiles |
| [16-rate-limiting.md](16-rate-limiting.md) | Redis-backed per-endpoint rate limits |

### Authentication & identity
| Spec | Contents |
|---|---|
| [20-oauth-server.md](20-oauth-server.md) | Built-in OAuth 2.1 server for MCP clients (CIMD + DCR, PKCE, RFC 9207, introspection) |
| [21-admin-auth.md](21-admin-auth.md) | OIDC-only admin login |
| [22-api-keys.md](22-api-keys.md) | API keys for non-OAuth clients |
| [23-upstream-oauth.md](23-upstream-oauth.md) | OAuth toward protected upstreams, per-(server,user) tokens, issuer validation |
| [24-identity-forwarding.md](24-identity-forwarding.md) | Header forwarding + `X-MCP-User` |

### Runtime & platform
| Spec | Contents |
|---|---|
| [30-session-management.md](30-session-management.md) | Restart-safe, replica-agnostic handshake sessions; stateless modern requests |
| [31-middleware.md](31-middleware.md) | Tool-call middleware chain + metering hook |
| [32-protocol-passthrough.md](32-protocol-passthrough.md) | Full bidirectional MCP proxy across protocol eras (dialects, MRTR bridge, subscriptions) |
| [33-state-propagation.md](33-state-propagation.md) | Cross-replica config invalidation |
| [40-management-api.md](40-management-api.md) | Service-authenticated REST management API |
| [41-bootstrap.md](41-bootstrap.md) | Idempotent startup provisioning |
| [42-export-import.md](42-export-import.md) | Config export/import |

### Operations & UI
| Spec | Contents |
|---|---|
| [50-audit-log.md](50-audit-log.md) | Per-tool-call audit records |
| [51-observability.md](51-observability.md) | Logs, metrics, health probes |
| [52-live-logs.md](52-live-logs.md) | Live log stream in the UI |
| [53-inspector.md](53-inspector.md) | Built-in MCP inspector |
| [60-admin-ui.md](60-admin-ui.md) | Nuxt 4 admin frontend |
| [61-docs-and-onboarding.md](61-docs-and-onboarding.md) | User-facing docs, client guides, demo seed |
| [62-architecture-documentation.md](62-architecture-documentation.md) | arc42 + ADRs + LikeC4 (docs/ tree) |

### Cross-cutting
| Spec | Contents |
|---|---|
| [70-security.md](70-security.md) | Threat model, SSRF egress policy, CORS/CSRF, limits |
| [71-deployment.md](71-deployment.md) | Public URL/proxy trust, migrations, upgrades, backups, CI/CD |

## Decision log — deliberately dropped from metamcp

These metamcp features were reviewed and **rejected** for bundlemcp. They are
recorded here so nobody re-proposes them without new evidence.

| Dropped | Why |
|---|---|
| **STDIO upstream servers** | Biggest complexity driver in metamcp (process spawning, crash tracking, env plumbing, fat image). Wrap stdio servers in a Streamable-HTTP sidecar instead — pattern documented in [10-server-registry.md](10-server-registry.md). |
| **SSE upstream & downstream transport** | Deprecated by the MCP spec; all targeted upstreams and clients speak Streamable HTTP. |
| **OpenAPI REST bridge** (`/api` per endpoint) | Notable build effort, not needed for the target clients (claude.ai, ChatGPT, MCP-native tools). |
| **Query-parameter API-key auth** | Keys leak into logs/URLs; header auth only. |
| **Multi-user resource ownership** (public/private per user) | bundlemcp is a single shared workspace — every admin sees and manages everything. Tenanting is the application layer's job. |
| **Admin tools over MCP** (~40 `metamcp-admin__*` tools) | The management REST API covers automation; agents can call REST. |
| **i18n** | English-only admin UI. |
| **Local password accounts** (better-auth style) | Admin login is OIDC-only; bundlemcp never stores passwords. |
| **Marketplace/search page** (metamcp's registry-browse UI) | bundlemcp is not a marketplace (00-overview non-goal); servers arrive via API/UI/bootstrap. |
| **`/oauth/userinfo` endpoint** | Introspection's `sub` covers all known consumers; no OIDC-provider surface ([20-oauth-server.md](20-oauth-server.md) out-of-scope). |
| **Opportunistic discovery on live `tools/list`** (metamcp's sync-on-list) | bundlemcp serves an endpoint's `tools/list` from the Postgres cache ([DISC-4](11-tool-discovery.md)), so no live upstream `tools/list` happens to piggy-back on. A periodic refresh ([DISC-7](11-tool-discovery.md), [ADR-0038](../docs/adr/0038-periodic-tool-refresh.md)) keeps the cache current instead. |

## Roadmap — deferred, not dropped

| Item | Status |
|---|---|
| **metamcp migration importer** — one-shot CLI reading a metamcp Postgres DB and mapping servers→registry, namespaces→bundles (+curation), endpoints→endpoints | Deferred by decision (2026-07). Revisit when bundlemcp reaches feature parity; until then migration is manual/bootstrap-file based. |
| **ChatGPT `search`/`fetch` connector profile** | Possible fourth endpoint profile ([15-endpoint-profiles.md](15-endpoint-profiles.md) out-of-scope). |

## Prior art

Specs cite these read-only reference repos (sibling checkouts):

- `../metamcp` — the fork being replaced; schema at
  `apps/backend/src/db/schema.ts`, gateway at `apps/backend/src/lib/metamcp/`,
  OAuth server at `apps/backend/src/routers/oauth/`.
- The first consumer, a private application layer, is not named in this repo;
  its registrar client and its metering router are the contracts specs 40 and
  31 were written against.
