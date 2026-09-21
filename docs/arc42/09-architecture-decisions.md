# 9. Architecture Decisions

Decisions are recorded as ADRs in [`../adr/`](../adr/README.md) — MADR-style
(Status / Context / Decision drivers / Decision / Alternatives considered /
Consequences), append-only, written
in the same PR as the change they govern
([ADOC-2/ADOC-5](../../spec/62-architecture-documentation.md)).

| ADR | Decision | Consequence in one line |
|---|---|---|
| [0001](../adr/0001-rewrite-not-fork.md) | Rewrite, don't fork metamcp | Own the architecture; accept re-implementation cost |
| [0002](../adr/0002-fastmcp-v3.md) | FastMCP v3 | Framework plumbing for free; session-model spike required |
| [0003](../adr/0003-sqlmodel-pydantic-first.md) | SQLModel / Pydantic-first | One shape definition, DB → generated TS |
| [0004](../adr/0004-postgres-redis-state-split.md) | Postgres durable / Redis live | Any-replica sessions; Redis becomes availability-critical |
| [0005](../adr/0005-streamable-http-only.md) | Streamable HTTP only | No process management; stdio via sidecar |
| [0006](../adr/0006-oidc-only-admin-auth.md) | OIDC-only admin auth | No password surface; IdP is a hard dependency |
| [0007](../adr/0007-endpoint-profiles.md) | Endpoint profiles | One bundle, per-client surfaces; chatgpt annotations lie deliberately |
| [0008](../adr/0008-full-bidirectional-proxy.md) | Full bidirectional proxy | No protocol degradation; hardest engineering item |
| [0009](../adr/0009-endpoint-bound-tokens-consent.md) | Consent + endpoint-bound tokens | Token confined to one endpoint; extra consent step |
| [0010](../adr/0010-single-workspace.md) | Single workspace | Simple model; no intra-instance tenanting |
| [0011](../adr/0011-own-streamable-http-edge.md) | Own the Streamable-HTTP edge (spike outcome) | Redis-backed sessions work; we own server-side protocol compliance |
| [0012](../adr/0012-per-call-upstream-connections.md) | Per-call upstream connections in v1 | Trivially correct identity isolation; pooling awaits OBS-6 data |
| [0013](../adr/0013-service-key-auth-first.md) | Service-key auth first | Headless management from day one; OIDC sessions now also shipped |
| [0014](../adr/0014-gateway-rendered-oauth-authlib.md) | Gateway-rendered auth pages; authlib RP; direct-DB tokens | claude.ai connectable without the UI; no introspect self-call |
| [0015](../adr/0015-keycloak-dev-idp.md) | Keycloak as the dev IdP | Integration tests prove real federation; heavier compose |
| [0016](../adr/0016-relay-design.md) | Protocol relay: registries + Redis signaling | Full bidirectional relay with any-replica correctness |
| [0017](../adr/0017-upstream-oauth-encryption.md) | Upstream OAuth client + token encryption | Protected upstreams work; tokens encrypted at rest with key rotation |
| [0018](../adr/0018-rate-limiting.md) | Redis fixed-window rate limiting + auth-failure lockout | Cross-replica abuse protection; per-IP credential-scan throttling |
| [0019](../adr/0019-api-service-layer.md) | Thin routers + service layer in the management API | Business logic in framework-free services; one DTO class per module |
| [0020](../adr/0020-library-level-service-layer.md) | Service + DTO layer at the library level; `apps/` for deployables | Services/DTOs are library peers any subsystem consumes; framework-free AuthService |
| [0021](../adr/0021-mcp-surface-completion.md) | Complete the MCP surface (prompts/resources/completions, capabilities, version, roots/logging) | Full-fidelity MCP request/response plane; live passthrough; push-between-calls pooling-dependent |
| [0022](../adr/0022-valkey-store.md) | Valkey (BSD-3) as the bundled RESP store, not Redis | Permissively-licensed store; redis-py client unchanged; RESP-generic |
| [0023](../adr/0023-import-contracts-and-shared-providers.md) | Import contracts enforce layer direction | Layering is checked in CI, not by review |
| [0024](../adr/0024-value-objects-and-rich-entities.md) | Value objects at the edge; behavior on entities | No tuples or dicts cross layers; rules live once; typed columns |
| [0025](../adr/0025-repository-unit-of-work-and-container.md) | Repository per entity, unit of work per request, typed container | Queries written once; invalidation after commit; atomic bootstrap; UPO-6 at all three edges |
| [0026](../adr/0026-controllers.md) | Controllers own an HTTP surface | Auth attached once per surface; the app factory lists surfaces |
| [0027](../adr/0027-mcp-edge-method-handlers.md) | Method registry in the MCP edge; tool call as a pipeline object | One handler class per JSON-RPC method; credentials and rendering written once |
| [0028](../adr/0028-oauth-server-as-services.md) | OAuth server as services with grant strategies | Thin OAuth controllers; typed single-use browser state; token store split by job |
| [0029](../adr/0029-dialects-and-dual-era-edge.md) | Protocol dialects; dual-era edge | Every client era ↔ every upstream era; a new revision is one dialect class |
| [0030](../adr/0030-fastmcp-4.md) | FastMCP 4 / SDK v2 upstream client | Modern upstreams reachable; era negotiated per server; snake_case SDK models |
| [0031](../adr/0031-joserfc-id-token-validation.md) | joserfc verifies ID tokens; `iss`/`aud` validated | Authlib's JOSE module is deprecated; the claim checks were silently skipped |
| [0032](../adr/0032-egress-policy-scope.md) | Egress policy on every outbound URL | Remote-named OAuth endpoints were unchecked; one SSRF gate |
| [0033](../adr/0033-clean-architecture-layers.md) | Four clean-architecture layers; contracts owned by the application | Any adapter is swappable and fakeable |
| [0034](../adr/0034-pydantic-entities-and-row-classes.md) | Entities are plain Pydantic models; row classes live in the persistence adapter | The domain imports no ORM; rows map generically |
| [0035](../adr/0035-front-controller-protocol-adapters-and-admission-pipeline.md) | Front Controller, Protocol Adapters (Stateless vs. Session), and Admission Pipeline | DoS defense by design; intrinsic era naming; decomposed router |
| [0037](../adr/0037-connect-account-tool.md) | Connect-account tool for per-user upstreams | A user with no tools yet can still connect; `tools/list` is per caller |

Smaller, spec-local decisions (dropped features and their reasons) live in the
[spec decision log](../../spec/README.md).
