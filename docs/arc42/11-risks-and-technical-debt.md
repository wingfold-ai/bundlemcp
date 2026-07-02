# 11. Risks and Technical Debt

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | **FastMCP v3 vs. externalized sessions** — the framework may assume in-process session objects, fighting the Redis-backed model (open questions in specs 30/32) | Core architecture rework if discovered late | First implementation spike is exactly this boundary; low-level SDK fallback sanctioned ([ADR-0002](../adr/0002-fastmcp-v3.md)) |
| 2 | **Bidirectional cross-replica relay complexity** (ADR-0008) — request/response correlation over pub/sub is the hardest subsystem | Schedule risk; subtle delivery bugs | Own spec with narrow requirements ([32](../../spec/32-protocol-passthrough.md)); integration tests per flow; capability gating limits blast radius |
| 3 | **Client behavior drift** — claude.ai/ChatGPT OAuth and annotation enforcement change over time | Endpoints stop connecting | Profiles isolate client quirks ([15](../../spec/15-endpoint-profiles.md)); OAS-9 integration test; open questions flag re-verification at implementation |
| 4 | **Redis as availability keystone** | Live traffic 503s during Redis outage | Accepted trade-off, explicitly specified (SES-14, RATE-6); ops guidance in [71](../../spec/71-deployment.md) |
| 5 | **SQLModel maturity** (0.0.x) | Missing ORM features | Escape hatch: SQLModel classes are SQLAlchemy models (spec/01 open question) |
| 6 | **chatgpt profile re-annotation** deliberately misdeclares write tools as read-safe | User surprise / trust issues if unnoticed | Mandatory UI warning + full audit (PROF-3); documented in [ADR-0007](../adr/0007-endpoint-profiles.md) |
| 7 | **Latest-stable policy churn** | Breaking upgrades arrive continuously | Min-version pins + CI gate; specs are framework-agnostic |

## Known technical debt (accepted, tracked)

- No metamcp-migration importer — manual migration for the primary user
  ([roadmap](../../spec/README.md)).
- Prompts/resources are uncurated passthrough (BND-8) — no per-bundle
  curation like tools have.
- Single scope in OAuth; audience-only binding (OAS-10) — fine-grained scopes
  deferred.
- Inspector covers tools only (spec/53 out-of-scope list).
