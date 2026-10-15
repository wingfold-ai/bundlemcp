# 4. Solution Strategy

| Quality goal / problem | Strategy | Where |
|---|---|---|
| Restart-safe, any-replica sessions | "A session is data, not an object": session records + upstream bindings in Redis; live streams replica-pinned with pub/sub routing between replicas; durable config only in Postgres | [ADR-0004](../adr/0004-postgres-redis-state-split.md), [sessions spec](../../openspec/specs/sessions/spec.md) |
| Full proxy fidelity | Relay the whole MCP surface bidirectionally (progress, cancellation, sampling/elicitation), capability-gated | [ADR-0008](../adr/0008-full-bidirectional-proxy.md), [protocol spec](../../openspec/specs/protocol/spec.md) |
| Per-client shaping | N endpoints per bundle × built-in profiles (default / oauth_only / write_as_read) implemented as middleware transforms | [ADR-0007](../adr/0007-endpoint-profiles.md), [endpoints spec](../../openspec/specs/endpoints/spec.md) |
| Clean app-layer integration | Service-authenticated REST API (UI uses the same API — automation parity) + a versioned metering-hook protocol | [management spec](../../openspec/specs/management/spec.md), [protocol spec](../../openspec/specs/protocol/spec.md) |
| Authorization correctness | OAuth 2.1 with DCR/PKCE, consent, endpoint-bound tokens (RFC 8707); OIDC-only humans | [ADR-0009](../adr/0009-endpoint-bound-tokens-consent.md), [ADR-0006](../adr/0006-oidc-only-admin-auth.md) |
| Type-safety end to end | Pydantic entity → SQLModel row → Pydantic DTO → OpenAPI → generated TS client | [ADR-0034](../adr/0034-pydantic-entities-and-row-classes.md) |
| Complexity budget | Aggressive scope cuts (stdio/SSE, REST bridge, multi-tenancy, i18n — decision log); single workspace | [ADR-0005](../adr/0005-streamable-http-only.md), [ADR-0010](../adr/0010-single-workspace.md) |
| Stay maintainable long-term | Latest-stable version policy; spec-first process (behavior change ⇒ spec change ⇒ ADR when architectural) | ARC-1, [documentation spec](../../openspec/specs/documentation/spec.md) |
