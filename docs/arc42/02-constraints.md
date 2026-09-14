# 2. Constraints

| Constraint | Rationale / source |
|---|---|
| Python ≥ 3.13 backend, Nuxt 4 frontend | Maintainer's home stack ([ADR-0001](../adr/0001-rewrite-not-fork.md)) |
| FastMCP v4, SQLModel, Postgres + Redis, Nuxt UI v4 | [spec/01](../../spec/01-architecture.md) stack table; [ADR-0002](../adr/0002-fastmcp-v3.md)–[0004](../adr/0004-postgres-redis-state-split.md), [ADR-0030](../adr/0030-fastmcp-4.md) |
| **Latest stable versions, always** (min-version pins) | Standing rule ARC-1 |
| Pydantic-first: one definition from DB row to generated TS type | ARC-3/ARC-4; [ADR-0003](../adr/0003-sqlmodel-pydantic-first.md) |
| Streamable HTTP only (up- and downstream) | [ADR-0005](../adr/0005-streamable-http-only.md) |
| External OIDC IdP required; no local passwords | [ADR-0006](../adr/0006-oidc-only-admin-auth.md) |
| No in-memory-only state a request depends on | ARC-9 — the core architectural rule |
| Docker-Compose-first deployment; TLS at the operator's proxy | ARC-13, [spec/71](../../spec/71-deployment.md) |
| MCP specification (current revision), OAuth 2.1, RFC 7591/7662/7009/8414/8707 | Protocol/interop conformance ([spec/20](../../spec/20-oauth-server.md), [spec/32](../../spec/32-protocol-passthrough.md)) |
| Billing, IdP, container discovery stay OUT (application layer) | Boundary table in [spec/00](../../spec/00-overview.md) |
| Hermetic unit tests + ruff gate every change | ARC-14 |
