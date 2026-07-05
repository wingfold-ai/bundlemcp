# bundlemcp — Specifications

bundlemcp is a self-hostable **MCP bundling gateway**: register upstream MCP
servers, compose them into **bundles**, and expose each bundle through one or
more **endpoints** tailored to the consuming client (claude.ai, ChatGPT, plain
API clients). It is a focused Python/Nuxt rewrite of the bundling core of
[metamcp](https://github.com/metatool-ai/metamcp), designed from day one for
restart-safe sessions and horizontal scaling, and built to be consumed by an
application layer (e.g. [ultra-mcp](https://github.com/mhoegger/ultra-mcp))
that adds its own identity provider, billing, and discovery on top.

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
| [00-overview.md](00-overview.md) | Vision, scope, boundary with ultra-mcp |
| [01-architecture.md](01-architecture.md) | Stack, version policy, repo layout, state model, Pydantic-first data flow |
| [02-domain-model.md](02-domain-model.md) | Entities and relationships |

### Bundling core
| Spec | Contents |
|---|---|
| [10-server-registry.md](10-server-registry.md) | Upstream MCP server CRUD (Streamable HTTP only) |
| [11-tool-discovery.md](11-tool-discovery.md) | Tool discovery and Postgres cache |
| [12-bundles.md](12-bundles.md) | Bundle composition, tool prefixing, collisions |
| [13-tool-management.md](13-tool-management.md) | Per-bundle tool enable/disable + overrides |
| [14-endpoints.md](14-endpoints.md) | Public endpoints, N per bundle, auth modes |
| [15-endpoint-profiles.md](15-endpoint-profiles.md) | claude.ai / chatgpt / default profiles |
