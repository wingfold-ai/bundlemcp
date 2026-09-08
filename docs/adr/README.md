# Architecture Decision Records

MADR-style records: **Status / Context / Decision drivers / Decision / Alternatives considered / Consequences** (Consequences split into Positive and Trade-offs).
Append-only — a superseding decision adds a new ADR and flips the old one to
`superseded by NNNN`. Indexed from [arc42 §9](../arc42/09-architecture-decisions.md);
process rules in [spec/62](../../spec/62-architecture-documentation.md) (ADOC-2, ADOC-5).

| # | Decision | Status |
|---|---|---|
| [0001](0001-rewrite-not-fork.md) | Rewrite metamcp's bundling core, don't fork | accepted |
| [0002](0002-fastmcp-v3.md) | FastMCP v3 as the MCP framework | accepted (amended by 0030) |
| [0003](0003-sqlmodel-pydantic-first.md) | SQLModel / Pydantic-first typing end to end | accepted (amended by 0033, 0034) |
| [0004](0004-postgres-redis-state-split.md) | Postgres = durable, Redis = live state | accepted |
| [0005](0005-streamable-http-only.md) | Streamable HTTP only (no stdio/SSE) | accepted |
| [0006](0006-oidc-only-admin-auth.md) | OIDC-only admin authentication | accepted |
| [0007](0007-endpoint-profiles.md) | Endpoint profiles incl. ChatGPT re-annotation | accepted |
| [0008](0008-full-bidirectional-proxy.md) | Full bidirectional MCP proxy fidelity | accepted |
| [0009](0009-endpoint-bound-tokens-consent.md) | OAuth consent + endpoint-bound tokens | accepted |
| [0010](0010-single-workspace.md) | Single shared workspace, no multi-tenancy | accepted |
| [0011](0011-own-streamable-http-edge.md) | Own the Streamable-HTTP edge; FastMCP upstream-only | accepted (amended by 0029) |
| [0012](0012-per-call-upstream-connections.md) | Per-call upstream connections in v1 | accepted |
| [0013](0013-service-key-auth-first.md) | Service-key auth first; admin OIDC with the UI | accepted (updated: OIDC sessions now shipped) |
| [0014](0014-gateway-rendered-oauth-authlib.md) | Gateway-rendered auth pages; authlib RP; direct-DB token validation | accepted (amended by 0031) |
| [0015](0015-keycloak-dev-idp.md) | Keycloak as the bundled dev IdP | accepted |
| [0016](0016-relay-design.md) | Protocol-relay: per-replica registries + Redis signaling | accepted (amended by 0029) |
| [0017](0017-upstream-oauth-encryption.md) | Upstream OAuth client + token encryption at rest | accepted |
| [0018](0018-rate-limiting.md) | Redis fixed-window rate limiting + auth-failure lockout | accepted |
| [0019](0019-api-service-layer.md) | Thin routers + service layer in the management API | accepted (amended by 0020) |
| [0020](0020-library-level-service-layer.md) | Service + DTO layer at the library level; `apps/` for deployables | accepted (amended by 0033) |
| [0021](0021-mcp-surface-completion.md) | Complete the MCP surface: prompts/resources/completions passthrough, capability aggregation, version negotiation, roots/logging relay | accepted (amended by 0029) |
| [0022](0022-valkey-store.md) | Valkey (BSD-3) as the bundled RESP store, not Redis | accepted |
| [0023](0023-import-contracts-and-shared-providers.md) | Import contracts enforce layer direction; shared providers at library level | accepted (amended by 0033) |
| [0024](0024-value-objects-and-rich-entities.md) | Value objects for what crosses the edge; behavior on the entities that own it | accepted |
| [0025](0025-repository-unit-of-work-and-container.md) | A repository per entity, a unit of work per request, one typed container | accepted (amended by 0033) |
| [0026](0026-controllers.md) | Controllers own an HTTP surface | accepted |
| [0027](0027-mcp-edge-method-handlers.md) | The MCP edge dispatches through a method registry; a tool call is an object | accepted |
| [0028](0028-oauth-server-as-services.md) | The OAuth server is services with grant strategies; browser state is typed and single-use | accepted |
| [0029](0029-dialects-and-dual-era-edge.md) | Protocol dialects: one edge serves every MCP revision; MRTR by pass-through or park-and-resume | accepted |
| [0030](0030-fastmcp-4.md) | FastMCP 4 / SDK v2 upstream client, protocol era negotiated per server | accepted |
| [0031](0031-joserfc-id-token-validation.md) | joserfc verifies ID tokens; issuer and audience validated explicitly | accepted |
| [0032](0032-egress-policy-scope.md) | The egress policy governs every outbound URL, not only MCP transport | accepted |
| [0033](0033-clean-architecture-layers.md) | Four clean-architecture layers; contracts owned by the application; SQLModel entities as the accepted deviation | accepted (amended by 0034) |
| [0034](0034-pydantic-entities-and-row-classes.md) | Entities are plain Pydantic models; the persistence adapter owns the row classes | accepted |
