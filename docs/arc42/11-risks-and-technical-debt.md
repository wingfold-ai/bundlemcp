# 11. Risks and Technical Debt

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | ~~FastMCP v3 vs. externalized sessions~~ **Resolved** by the implementation spike: the endpoint edge is owned directly (FastAPI + Redis records), FastMCP serves the upstream side ([ADR-0011](../adr/0011-own-streamable-http-edge.md)) | — | Residual risk moved to #2 (the relay work now happens on our own edge) |
| 2 | ~~Bidirectional cross-replica relay complexity~~ **Design landed** ([ADR-0016](../adr/0016-relay-design.md)): publish-only Redis bus + per-replica registries; progress/cancel/elicitation proven cross-replica in hermetic two-instance tests. Residual = claude.ai/ChatGPT *behavioral* verification against real clients | Lower now | Loopback-server relay suite; compose integration; capability gating limits blast radius |
| 3 | **Client behavior drift** — claude.ai/ChatGPT OAuth and annotation enforcement change over time | Endpoints stop connecting | Profiles isolate client quirks ([15](../../openspec/specs/endpoints/spec.md)); AUTH-9 integration test; open questions flag re-verification at implementation |
| 4 | **Redis as availability keystone** | Live traffic 503s during Redis outage | Accepted trade-off, explicitly specified (SES-14, EP-21); ops guidance in [71](../../openspec/specs/deployment/spec.md) |
| 5 | **SQLModel maturity** (0.0.x) | Missing ORM features | Escape hatch: the row classes in `infrastructure/postgres/rows/` are SQLAlchemy models; entities never touch the ORM ([ADR-0034](../adr/0034-pydantic-entities-and-row-classes.md)) |
| 6 | **write_as_read profile re-annotation** deliberately misdeclares write tools as read-safe | User surprise / trust issues if unnoticed | Mandatory UI warning + full audit (EP-12); documented in [ADR-0007](../adr/0007-endpoint-profiles.md) |
| 7 | **Latest-stable policy churn** | Breaking upgrades arrive continuously | Min-version pins + CI gate; specs are framework-agnostic |
| 8 | **Protocol-era drift** — MCP 2026-07-28 removed sessions, the handshake and server-initiated requests; major clients adopt at different speeds (Copilot modern, Claude/ChatGPT/Gemini/Cursor handshake as of 2026-09) | An edge on one era loses the other's clients | Dual-era edge with one dialect per revision ([ADR-0029](../adr/0029-dialects-and-dual-era-edge.md)); conformance suite per revision in CI; `legacy_protocol_enabled` to retire the handshake era |
| 9 | **Park-and-resume MRTR** ([PROT-18](../../openspec/specs/protocol/spec.md)) pins an in-flight upstream call to a replica between a modern client's two requests | Replica loss mid-elicitation | Bounded by the call's timeout budget; re-run fallback answers the retry; pass-through (no pinning) whenever the upstream is modern |

## Known technical debt (accepted, tracked)

- No metamcp-migration importer — manual migration for the primary user
  ([roadmap](../../openspec/README.md)).
- A member's prompts/resources are uncurated live passthrough (BND-8, [ADR-0021](../adr/0021-mcp-surface-completion.md))
  — by design no per-bundle curation like tools have, which would need prompt/resource discovery (BND-37, optional). A
  bundle adds context of its own instead: prompts and resources authored on the bundle and served without upstream
  contact ([ADR-0044](../adr/0044-bundle-owned-prompts-and-resources.md)).
- **Upstream→client push between calls is pooling-dependent** ([ADR-0021](../adr/0021-mcp-surface-completion.md)):
  `resources/subscribe` updates, PROT-7 upstream log push, and PROT-10 upstream `list_changed` outside an active call
  need a persistent upstream connection that the per-call model (ADR-0012) lacks. None of them is delivered today,
  neither between calls nor within one, so none is advertised either: a member's `resources.subscribe` and its prompt
  and resource `listChanged` are dropped from the bundle's capabilities (PROT-11) until pooling (SES-8, change
  `add-upstream-session-pooling`) delivers them.
- `subscriptions/listen` delivers prompt/resource list changes only for the bundle's own entries
  ([PROT-17](../../openspec/specs/protocol/spec.md), BND-28) — a member's list changes and resource
  subscriptions wait for the same pooling.
- Protocol extensions (Tasks, MCP Apps) are not proxied and not advertised (PROT-11).
- Single scope in OAuth; audience-only binding (AUTH-10) — fine-grained scopes deferred.
- There is no built-in inspector yet (change `add-inspector`).
- Rate limiting ([endpoints spec](../../openspec/specs/endpoints/spec.md), [ADR-0018](../adr/0018-rate-limiting.md))
  uses a fixed-window counter — up to a 2× burst at window edges; a sliding-window log is the noted upgrade.
- The `application/contracts/` package holds protocols for in-process objects (`StreamRegistry`, `GatewayMetrics`) as
  well as for stores; they exist so the MCP edge names no adapter and can be faked, not because a second implementation
  is planned ([ADR-0033](../adr/0033-clean-architecture-layers.md)).
