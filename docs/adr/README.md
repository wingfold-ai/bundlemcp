# Architecture Decision Records

MADR-style records: **Status / Context / Decision drivers / Decision / Alternatives considered / Consequences**
(Consequences split into Positive and Trade-offs). Append-only: a later decision never edits an earlier record's
Context, Decision or Consequences, only its `**Status:**` line. Two states express that, after an optional `proposed`:

| Status | Meaning |
|---|---|
| `proposed` | Written with a `Draft` spec and under review; not yet authoritative. Becomes `accepted` when the spec does. |
| `accepted` | Still authoritative. `**Amended by:** NNNN` means part of it was revised — read both, newest last. |
| `superseded by NNNN` | Wholly replaced. Do not follow it; it is kept for the reasoning only. |

Every `**Amends:**` has a matching `**Amended by:**` on its target, and the
index below is generated from those lines, so file and index cannot disagree.
Indexed from [arc42 §9](../arc42/09-architecture-decisions.md); process rules in
[spec/62](../../openspec/specs/documentation/spec.md) (DOC-8, DOC-11).

| # | Decision | Status |
|---|---|---|
| [0001](0001-rewrite-not-fork.md) | Rewrite metamcp's bundling core, don't fork | accepted |
| [0002](0002-fastmcp-v3.md) | FastMCP v3 as the MCP framework | superseded by 0030 |
| [0003](0003-sqlmodel-pydantic-first.md) | SQLModel / Pydantic-first typing end to end | accepted (amended by 0024, 0033, 0034) |
| [0004](0004-postgres-redis-state-split.md) | Postgres = durable, Redis = live state | accepted |
| [0005](0005-streamable-http-only.md) | Streamable HTTP only (no stdio/SSE) | accepted |
| [0006](0006-oidc-only-admin-auth.md) | OIDC-only admin authentication | accepted |
| [0007](0007-endpoint-profiles.md) | Endpoint profiles incl. ChatGPT re-annotation | accepted (amended by 0046, 0047) |
| [0008](0008-full-bidirectional-proxy.md) | Full bidirectional MCP proxy fidelity | accepted |
| [0009](0009-endpoint-bound-tokens-consent.md) | OAuth consent + endpoint-bound tokens | accepted |
| [0010](0010-single-workspace.md) | Single shared workspace, no multi-tenancy | accepted |
| [0011](0011-own-streamable-http-edge.md) | Own the Streamable-HTTP edge; FastMCP upstream-only | accepted (amended by 0027, 0029, 0035) |
| [0012](0012-per-call-upstream-connections.md) | Per-call upstream connections in v1 | superseded by 0054 (amended by 0030) |
| [0013](0013-service-key-auth-first.md) | Service-key auth first; admin OIDC with the UI | accepted (OIDC sessions have since shipped) |
| [0014](0014-gateway-rendered-oauth-authlib.md) | Gateway-rendered auth pages; authlib RP; direct-DB token validation | accepted (amended by 0028, 0031, 0036, 0065) |
| [0015](0015-keycloak-dev-idp.md) | Keycloak as the bundled dev IdP | accepted |
| [0016](0016-relay-design.md) | Protocol-relay: per-replica registries + Redis signaling | accepted (amended by 0027, 0029) |
| [0017](0017-upstream-oauth-encryption.md) | Upstream OAuth client + token encryption at rest | accepted (amended by 0028, 0037, 0040, 0061) |
| [0018](0018-rate-limiting.md) | Redis fixed-window rate limiting + auth-failure lockout | accepted |
| [0019](0019-api-service-layer.md) | Thin routers + service layer in the management API | accepted (amended by 0020, 0026) |
| [0020](0020-library-level-service-layer.md) | Service + DTO layer at the library level; `apps/` for deployables | accepted (amended by 0023, 0025, 0033) |
| [0021](0021-mcp-surface-completion.md) | Complete the MCP surface: prompts/resources/completions passthrough, capability aggregation, version negotiation, roots/logging relay | accepted (amended by 0029, 0043, 0044, 0054, 0056) |
| [0022](0022-valkey-store.md) | Valkey (BSD-3) as the bundled RESP store, not Redis | accepted |
| [0023](0023-import-contracts-and-shared-providers.md) | Import contracts enforce layer direction; shared providers at library level | accepted (amended by 0025, 0033) |
| [0024](0024-value-objects-and-rich-entities.md) | Value objects for what crosses the edge; behavior on the entities that own it | accepted |
| [0025](0025-repository-unit-of-work-and-container.md) | A repository per entity, a unit of work per request, one typed container | accepted (amended by 0033) |
| [0026](0026-controllers.md) | Controllers own an HTTP surface | accepted (amended by 0027, 0028) |
| [0027](0027-mcp-edge-method-handlers.md) | The MCP edge dispatches through a method registry; a tool call is an object | accepted (amended by 0029, 0035) |
| [0028](0028-oauth-server-as-services.md) | The OAuth server is services with grant strategies; browser state is typed and single-use | accepted (amended by 0036) |
| [0029](0029-dialects-and-dual-era-edge.md) | Protocol dialects: one edge serves every MCP revision; MRTR by pass-through or park-and-resume | accepted (amended by 0035) |
| [0030](0030-fastmcp-4.md) | FastMCP 4 / SDK v2 upstream client, protocol era negotiated per server | accepted |
| [0031](0031-joserfc-id-token-validation.md) | joserfc verifies ID tokens; issuer and audience validated explicitly | accepted |
| [0032](0032-egress-policy-scope.md) | The egress policy governs every outbound URL, not only MCP transport | accepted |
| [0033](0033-clean-architecture-layers.md) | Four clean-architecture layers; contracts owned by the application; SQLModel entities as the accepted deviation | accepted (amended by 0034) |
| [0034](0034-pydantic-entities-and-row-classes.md) | Entities are plain Pydantic models; the persistence adapter owns the row classes | accepted |
| [0035](0035-front-controller-protocol-adapters-and-admission-pipeline.md) | Front Controller, Protocol Adapters (Stateless vs. Session), and Admission Pipeline at the MCP Edge | accepted |
| [0036](0036-oauth-slice-decomposition-and-shared-contracts.md) | The OAuth slice decomposes into resolution, consent and issuance; clock, hasher and generator become contracts | accepted |
| [0037](0037-connect-account-tool.md) | A gateway-provided connect-account tool for per-user upstreams | accepted |
| [0038](0038-periodic-tool-refresh.md) | A periodic sweep keeps the tool cache current | accepted |
| [0039](0039-server-inspection-and-connection-state.md) | Upstreams are inspected, and their refusals classified, below the MCP client | accepted |
| [0040](0040-upstream-client-identification.md) | The gateway identifies itself upstream in the MCP spec's order | accepted |
| [0041](0041-delegated-upstream-tokens.md) | Delegated tokens replace token passthrough for identity-aware upstreams | accepted |
| [0042](0042-http-metering-hook-and-outcome-kinds.md) | The metering hook can run out of process, and reports outcome kinds | accepted (amended by 0050) |
| [0043](0043-contact-upstreams-only-with-a-reason.md) | The gateway contacts an upstream only when it has a reason to | accepted (amended by 0059) |
| [0044](0044-bundle-owned-prompts-and-resources.md) | Bundles own prompts and resources, served by the gateway | accepted |
| [0045](0045-upstreams-on-the-published-surface.md) | The published surface says "upstreams" | accepted |
| [0046](0046-profiles-as-registered-presets-and-tool-pipeline-stages.md) | Profiles are registered presets; the served tool set is built by ordered stages | accepted (amended by 0050) |
| [0047](0047-profiles-named-for-what-they-change.md) | Profiles are named for what they change | accepted |
| [0048](0048-egress-policy-enforced-at-connect-time.md) | The egress policy is enforced at connect time | accepted |
| [0049](0049-browser-origins-are-an-endpoint-setting.md) | Browser origins are an endpoint setting, not an auth mode | accepted |
| [0050](0050-one-stage-chain-and-once-per-invocation-metering.md) | Tools pass one stage chain, and an invocation is metered once | accepted |
| [0051](0051-request-context-readiness-report-and-optional-tracing.md) | Requests carry one log context, readiness reports each check, and tracing is optional | accepted |
| [0052](0052-per-replica-prometheus-metrics-with-a-closed-label-set.md) | Each replica exports Prometheus metrics, behind management credentials, with a closed label set | accepted |
| [0053](0053-audit-durability-and-the-idempotency-key-join.md) | The audit log is written durably, names every loss by idempotency key, and is purged by retention | accepted |
| [0054](0054-upstream-session-pooling.md) | Upstream sessions are pooled per replica and continued from the session record | accepted |
| [0055](0055-export-and-bootstrap-share-one-document.md) | Export, import and bootstrap share one document, with secrets as placeholders | accepted |
| [0056](0056-member-listings-cached-for-curation-only.md) | Members' prompts and resources are cached at discovery, for curation only | accepted (amended by 0059) |
| [0057](0057-live-logs-through-a-capped-valkey-stream.md) | Live logs fan out through a capped Valkey stream | accepted |
| [0058](0058-inspector-proxied-by-the-management-api.md) | The inspector is proxied by the management API, and reaches endpoints in-process | accepted |
| [0059](0059-member-lists-served-from-the-discovery-snapshot.md) | Members' prompt and resource lists are served from the discovery snapshot | accepted |
| [0060](0060-unauthenticated-fetches-use-a-public-only-egress-scope.md) | Unauthenticated fetches use a public-only egress scope | accepted |
| [0061](0061-static-upstream-headers-encrypted-in-the-repository.md) | Static upstream headers are encrypted in the repository | accepted |
| [0062](0062-member-notifications-typed-at-the-pool-boundary.md) | Member notifications are typed at the pool boundary | accepted |
| [0063](0063-discovery-serialized-per-server-by-a-transaction-lock.md) | Discovery is serialized per server by a transaction-scoped lock | accepted (amended by 0064) |
| [0064](0064-discovery-writes-only-what-it-observed.md) | Discovery writes only what it observed, and a delete waits for it | accepted |
| [0065](0065-operator-branded-auth-pages.md) | Operators brand the auth pages with templates and same-origin assets | accepted |
| [0066](0066-scoped-service-keys.md) | Service keys can be limited to scopes, and every management route declares one | accepted |
