# 9. Architecture Decisions

Decisions are recorded as ADRs in [`../adr/`](../adr/README.md) — MADR-style (Status / Context / Decision drivers /
Decision / Alternatives considered / Consequences), append-only, written in the same PR as the change they govern
([ADOC-2/ADOC-5](../../spec/62-architecture-documentation.md)).

| ADR | Decision | Status | Consequence in one line |
|---|---|---|---|
| [0001](../adr/0001-rewrite-not-fork.md) | Rewrite, don't fork metamcp | accepted | Own the architecture; accept re-implementation cost |
| [0002](../adr/0002-fastmcp-v3.md) | FastMCP v3 | superseded by 0030 | Framework plumbing for free; session-model spike required |
| [0003](../adr/0003-sqlmodel-pydantic-first.md) | SQLModel / Pydantic-first | accepted (amended by 0024, 0033, 0034) | One shape definition, DB → generated TS |
| [0004](../adr/0004-postgres-redis-state-split.md) | Postgres durable / Redis live | accepted | Any-replica sessions; Redis becomes availability-critical |
| [0005](../adr/0005-streamable-http-only.md) | Streamable HTTP only | accepted | No process management; stdio via sidecar |
| [0006](../adr/0006-oidc-only-admin-auth.md) | OIDC-only admin auth | accepted | No password surface; IdP is a hard dependency |
| [0007](../adr/0007-endpoint-profiles.md) | Endpoint profiles | accepted | One bundle, per-client surfaces; chatgpt annotations lie deliberately |
| [0008](../adr/0008-full-bidirectional-proxy.md) | Full bidirectional proxy | accepted | No protocol degradation; hardest engineering item |
| [0009](../adr/0009-endpoint-bound-tokens-consent.md) | Consent + endpoint-bound tokens | accepted | Token confined to one endpoint; extra consent step |
| [0010](../adr/0010-single-workspace.md) | Single workspace | accepted | Simple model; no intra-instance tenanting |
| [0011](../adr/0011-own-streamable-http-edge.md) | Own the Streamable-HTTP edge (spike outcome) | accepted (amended by 0027, 0029, 0035) | Redis-backed sessions work; we own server-side protocol compliance |
| [0012](../adr/0012-per-call-upstream-connections.md) | Per-call upstream connections in v1 | accepted (amended by 0030) | Trivially correct identity isolation; pooling awaits OBS-6 data |
| [0013](../adr/0013-service-key-auth-first.md) | Service-key auth first | accepted (OIDC sessions have since shipped) | Headless management from day one; OIDC sessions now also shipped |
| [0014](../adr/0014-gateway-rendered-oauth-authlib.md) | Gateway-rendered auth pages; authlib RP; direct-DB tokens | accepted (amended by 0028, 0031, 0036) | claude.ai connectable without the UI; no introspect self-call |
| [0015](../adr/0015-keycloak-dev-idp.md) | Keycloak as the dev IdP | accepted | Integration tests prove real federation; heavier compose |
| [0016](../adr/0016-relay-design.md) | Protocol relay: registries + Redis signaling | accepted (amended by 0027, 0029) | Full bidirectional relay with any-replica correctness |
| [0017](../adr/0017-upstream-oauth-encryption.md) | Upstream OAuth client + token encryption | accepted (amended by 0028, 0037, 0040) | Protected upstreams work; tokens encrypted at rest with key rotation |
| [0018](../adr/0018-rate-limiting.md) | Redis fixed-window rate limiting + auth-failure lockout | accepted | Cross-replica abuse protection; per-IP credential-scan throttling |
| [0019](../adr/0019-api-service-layer.md) | Thin routers + service layer in the management API | accepted (amended by 0020, 0026) | Business logic in framework-free services; one DTO class per module |
| [0020](../adr/0020-library-level-service-layer.md) | Service + DTO layer at the library level; `apps/` for deployables | accepted (amended by 0023, 0025, 0033) | Services/DTOs are library peers any subsystem consumes; framework-free AuthService |
| [0021](../adr/0021-mcp-surface-completion.md) | Complete the MCP surface (prompts/resources/completions, capabilities, version, roots/logging) | accepted (amended by 0029, 0043) | Full-fidelity MCP request/response plane; live passthrough; push-between-calls pooling-dependent |
| [0022](../adr/0022-valkey-store.md) | Valkey (BSD-3) as the bundled RESP store, not Redis | accepted | Permissively-licensed store; redis-py client unchanged; RESP-generic |
| [0023](../adr/0023-import-contracts-and-shared-providers.md) | Import contracts enforce layer direction | accepted (amended by 0025, 0033) | Layering is checked in CI, not by review |
| [0024](../adr/0024-value-objects-and-rich-entities.md) | Value objects at the edge; behavior on entities | accepted | No tuples or dicts cross layers; rules live once; typed columns |
| [0025](../adr/0025-repository-unit-of-work-and-container.md) | Repository per entity, unit of work per request, typed container | accepted (amended by 0033) | Queries written once; invalidation after commit; atomic bootstrap; UPO-6 at all three edges |
| [0026](../adr/0026-controllers.md) | Controllers own an HTTP surface | accepted (amended by 0027, 0028) | Auth attached once per surface; the app factory lists surfaces |
| [0027](../adr/0027-mcp-edge-method-handlers.md) | Method registry in the MCP edge; tool call as a pipeline object | accepted (amended by 0029, 0035) | One handler class per JSON-RPC method; credentials and rendering written once |
| [0028](../adr/0028-oauth-server-as-services.md) | OAuth server as services with grant strategies | accepted (amended by 0036) | Thin OAuth controllers; typed single-use browser state; token store split by job |
| [0029](../adr/0029-dialects-and-dual-era-edge.md) | Protocol dialects; dual-era edge | accepted (amended by 0035) | Every client era ↔ every upstream era; a new revision is one dialect class |
| [0030](../adr/0030-fastmcp-4.md) | FastMCP 4 / SDK v2 upstream client | accepted | Modern upstreams reachable; era negotiated per server; snake_case SDK models |
| [0031](../adr/0031-joserfc-id-token-validation.md) | joserfc verifies ID tokens; `iss`/`aud` validated | accepted | Authlib's JOSE module is deprecated; the claim checks were silently skipped |
| [0032](../adr/0032-egress-policy-scope.md) | Egress policy on every outbound URL | accepted | Remote-named OAuth endpoints were unchecked; one SSRF gate |
| [0033](../adr/0033-clean-architecture-layers.md) | Four clean-architecture layers; contracts owned by the application | accepted (amended by 0034) | Any adapter is swappable and fakeable |
| [0034](../adr/0034-pydantic-entities-and-row-classes.md) | Entities are plain Pydantic models; row classes live in the persistence adapter | accepted | The domain imports no ORM; rows map generically |
| [0035](../adr/0035-front-controller-protocol-adapters-and-admission-pipeline.md) | Front Controller, Protocol Adapters (Stateless vs. Session), and Admission Pipeline | accepted | DoS defense by design; intrinsic era naming; decomposed router |
| [0036](../adr/0036-oauth-slice-decomposition-and-shared-contracts.md) | OAuth slice splits into client resolution, consent and code issuance; clock, hasher and generator are contracts | accepted | Expiry is testable without patching; an unauthenticated authorize writes nothing |
| [0037](../adr/0037-connect-account-tool.md) | Connect-account tool for per-user upstreams | accepted | A user with no tools yet can still connect; `tools/list` is per caller |
| [0038](../adr/0038-periodic-tool-refresh.md) | Periodic tool-cache sweep, one replica per interval | accepted | A server unreachable at registration heals on its own; every upstream is probed once per interval |
| [0039](../adr/0039-server-inspection-and-connection-state.md) | Inspect upstreams and classify refusals from HTTP evidence below the MCP client | accepted | Registration asks one question; operators see why a server fails and how to fix it |
| [0040](../adr/0040-upstream-client-identification.md) | Pre-registered → client metadata document → DCR; resource indicators, PKCE and issuer checks, step-up, client credentials | accepted | Conforms to MCP authorization 2026-07-28; CIMD needs an https gateway |
| [0041](../adr/0041-delegated-upstream-tokens.md) | Gateway-issued, audience-bound delegated tokens instead of token passthrough | accepted | Upstreams verify callers without holding their credential; one Valkey write per call |
| [0042](../adr/0042-http-metering-hook-and-outcome-kinds.md) | Out-of-process metering hook over HTTP; post-call reports outcome kinds | accepted | An out-of-process hook needs no custom image; hook contract v2 is breaking for in-process hooks |
| [0043](../adr/0043-contact-upstreams-only-with-a-reason.md) | Probe on upsert only when discovery inputs change; fan out only to members advertising the capability | accepted | Idle scale-to-zero upstreams stay asleep across deploys and client connects; a stale snapshot hides new prompts/resources until the next discovery |

Smaller, spec-local decisions (dropped features and their reasons) live in the
[spec decision log](../../spec/README.md).
