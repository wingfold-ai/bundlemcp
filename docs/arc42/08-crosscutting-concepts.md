# 8. Cross-cutting Concepts

## State model
Postgres = durable (system of record), Redis = live (sessions, limits,
pub/sub). No in-memory-only state a request depends on; caches exist only
under explicit invalidation ([spec/33](../../spec/33-state-propagation.md)).
Explicit degradation matrix for outages ([SES-14](../../spec/30-session-management.md)).

## Identity
One `User` per human, provisioned from OIDC `(issuer, sub)` regardless of
entry path (admin UI or connector authorize flow). The bundlemcp user id is
the stable `sub` everywhere: introspection, metering, audit, `X-MCP-User`.
Machine callers are API keys (`endpoint` vs `service` kind).

## Typing
Pydantic v2 everywhere: SQLModel entities → derived DTOs → OpenAPI →
generated TS client. Validation at every boundary; no hand-written duplicate
shapes ([ADR-0003](../adr/0003-sqlmodel-pydantic-first.md)).

## Security
Threat model + controls centralized in [spec/70](../../spec/70-security.md):
one egress-policy layer for all admin-supplied URLs (SSRF), CORS/CSRF rules,
size limits, DCR quotas, secret redaction (testable), tokens hashed /
upstream tokens encrypted with rotatable keys ([DEP-9](../../spec/71-deployment.md)).

## Error handling
Structured MCP errors to clients; no silent degradation — partial
`tools/list` responses increment a dedicated metric ([OBS-4](../../spec/51-observability.md));
middleware never swallows errors ([MID-5](../../spec/31-middleware.md));
upstream session loss is retried once, then surfaced ([SES-7](../../spec/30-session-management.md)).

## Observability
Structured JSON logs (redacted), Prometheus `/metrics`, `/healthz`+`/readyz`,
optional OTel; live-log ring in Redis for the UI; per-call audit records in
Postgres as the billing reconciliation source ([AUD-7](../../spec/50-audit-log.md)).

## Configuration
Deploy-time: `BUNDLEMCP_*` env via pydantic-settings. Runtime-tunable:
`Config` table, editable in UI, propagated via invalidation events
(timeouts, session lifetime, limits).

## Testing
Hermetic unit suite gates every change (ARC-14); integration suite proves the
architecture's promises: restart-under-load, two-replica round-robin,
upstream-restart recovery, propagation budget, OAuth happy path
(SES-12, STP-3, OAS-9); tests cite requirement IDs.
