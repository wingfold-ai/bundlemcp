# 9. Architecture Decisions

Decisions are recorded as ADRs in [`../adr/`](../adr/README.md) — MADR-style
(Status / Context / Decision / Reasons / Consequences), append-only, written
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

Smaller, spec-local decisions (dropped features and their reasons) live in the
[spec decision log](../../spec/README.md).
