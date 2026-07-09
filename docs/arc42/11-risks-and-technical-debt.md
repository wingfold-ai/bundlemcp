# 11. Risks and Technical Debt

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | **FastMCP v3 vs. externalized sessions** — the framework's session model may not tolerate session state living outside the process | Blocks the whole state model ([ADR-0004](../adr/0004-postgres-redis-state-split.md)) | Implementation spike before committing to the framework; owning the endpoint edge is the fallback |
| 2 | **Bidirectional cross-replica relay complexity** — progress, cancellation, sampling and elicitation must cross replicas | Highest engineering risk in the project | Design spike; capability gating limits blast radius if a piece is not ready |
| 3 | **Client behavior drift** — claude.ai/ChatGPT OAuth and annotation enforcement change over time | Endpoints stop connecting | Profiles isolate client quirks ([15](../../spec/15-endpoint-profiles.md)); OAS-9 integration test; open questions flag re-verification at implementation |
| 4 | **Redis as availability keystone** | Live traffic 503s during Redis outage | Accepted trade-off, explicitly specified (SES-14, RATE-6); ops guidance in [71](../../spec/71-deployment.md) |
| 5 | **SQLModel maturity** (0.0.x) | Missing ORM features | Escape hatch: SQLModel classes are SQLAlchemy models (spec/01 open question) |
| 6 | **chatgpt profile re-annotation** deliberately misdeclares write tools as read-safe | User surprise / trust issues if unnoticed | Mandatory UI warning + full audit (PROF-3); documented in [ADR-0007](../adr/0007-endpoint-profiles.md) |
| 7 | **Latest-stable policy churn** | Breaking upgrades arrive continuously | Min-version pins + CI gate; specs are framework-agnostic |

## Known technical debt (accepted, tracked)

- No metamcp-migration importer — manual migration for the primary user
  ([roadmap](../../spec/README.md)).
