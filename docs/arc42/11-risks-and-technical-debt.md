# 11. Risks and Technical Debt

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | ~~FastMCP v3 vs. externalized sessions~~ **Resolved** by the implementation spike: the endpoint edge is owned directly (FastAPI + Redis records), FastMCP serves the upstream side ([ADR-0011](../adr/0011-own-streamable-http-edge.md)) | — | Residual risk moved to #2 (the relay work now happens on our own edge) |
| 2 | ~~Bidirectional cross-replica relay complexity~~ **Design landed** ([ADR-0016](../adr/0016-relay-design.md)): publish-only Redis bus + per-replica registries; progress/cancel/elicitation proven cross-replica in hermetic two-instance tests. Residual = claude.ai/ChatGPT *behavioral* verification against real clients | Lower now | Loopback-server relay suite; compose integration; capability gating limits blast radius |
| 3 | **Client behavior drift** — claude.ai/ChatGPT OAuth and annotation enforcement change over time | Endpoints stop connecting | Profiles isolate client quirks ([15](../../spec/15-endpoint-profiles.md)); OAS-9 integration test; open questions flag re-verification at implementation |
| 4 | **Redis as availability keystone** | Live traffic 503s during Redis outage | Accepted trade-off, explicitly specified (SES-14, RATE-6); ops guidance in [71](../../spec/71-deployment.md) |
| 5 | **SQLModel maturity** (0.0.x) | Missing ORM features | Escape hatch: the row classes in `infrastructure/postgres/rows/` are SQLAlchemy models; entities never touch the ORM ([ADR-0034](../adr/0034-pydantic-entities-and-row-classes.md)) |
| 6 | **chatgpt profile re-annotation** deliberately misdeclares write tools as read-safe | User surprise / trust issues if unnoticed | Mandatory UI warning + full audit (PROF-3); documented in [ADR-0007](../adr/0007-endpoint-profiles.md) |
| 7 | **Latest-stable policy churn** | Breaking upgrades arrive continuously | Min-version pins + CI gate; specs are framework-agnostic |
| 8 | **Protocol-era drift** — MCP 2026-07-28 removed sessions, the handshake and server-initiated requests; major clients adopt at different speeds (Copilot modern, Claude/ChatGPT/Gemini/Cursor handshake as of 2026-09) | An edge on one era loses the other's clients | Dual-era edge with one dialect per revision ([ADR-0029](../adr/0029-dialects-and-dual-era-edge.md)); conformance suite per revision in CI; `legacy_protocol_enabled` to retire the handshake era |
| 9 | **Park-and-resume MRTR** ([PROT-18](../../spec/32-protocol-passthrough.md)) pins an in-flight upstream call to a replica between a modern client's two requests | Replica loss mid-elicitation | Bounded by the call's timeout budget; re-run fallback answers the retry; pass-through (no pinning) whenever the upstream is modern |

## Known technical debt (accepted, tracked)

- No metamcp-migration importer — manual migration for the primary user
  ([roadmap](../../spec/README.md)).
- A member's prompts/resources are uncurated live passthrough (BND-8, [ADR-0021](../adr/0021-mcp-surface-completion.md))
  — by design no per-bundle curation like tools have, which would need prompt/resource discovery (BPR-20, optional). A
  bundle adds context of its own instead: prompts and resources authored on the bundle and served without upstream
  contact ([ADR-0044](../adr/0044-bundle-owned-prompts-and-resources.md)).
- **Upstream→client push between calls is pooling-dependent** ([ADR-0021](../adr/0021-mcp-surface-completion.md)):
  `resources/subscribe` updates, PROT-7 upstream log push, and PROT-10 upstream `list_changed` outside an active call
  need a persistent upstream connection that the per-call model (ADR-0012) lacks. Advertised + delivered within an
  active-call window; full between-call push lands with connection pooling (SES-8).
- `subscriptions/listen` delivers prompt/resource list changes only for the bundle's own entries
  ([PROT-17](../../spec/32-protocol-passthrough.md), BPR-11) — a member's list changes and resource subscriptions wait
  for the same pooling.
- Protocol extensions (Tasks, MCP Apps) are not proxied and not advertised (PROT-11).
- Single scope in OAuth; audience-only binding (OAS-10) — fine-grained scopes deferred.
- Inspector covers tools only (spec/53 out-of-scope list).
- Rate limiting ([16](../../spec/16-rate-limiting.md), [ADR-0018](../adr/0018-rate-limiting.md)) uses a fixed-window
  counter — up to a 2× burst at window edges; a sliding-window log is the noted upgrade. Its rejection/lockout counters
  are in-process; the Prometheus `/metrics` export is still pending (spec 51).
- The `application/contracts/` package holds protocols for in-process objects (`StreamRegistry`, `Counters`) as well as
  for stores; they exist so the MCP edge names no adapter and can be faked, not because a second implementation is
  planned ([ADR-0033](../adr/0033-clean-architecture-layers.md)).
