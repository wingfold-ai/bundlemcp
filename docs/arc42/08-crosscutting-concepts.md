# 8. Cross-cutting Concepts

## State model
Postgres = durable (system of record), Redis = live (sessions, limits, pub/sub). No in-memory-only state a request
depends on; caches exist only under explicit invalidation
([sessions spec](../../openspec/specs/sessions/spec.md)). Explicit degradation matrix for outages
([SES-14](../../openspec/specs/sessions/spec.md)). Pooled upstream sessions are a per-replica transport cache: the
session record's binding holds what any replica needs to continue one (upstream session id, version, config
fingerprint, identity key — never a header value), so losing a replica costs at most an upstream re-initialize
([SES-5](../../openspec/specs/sessions/spec.md), [ADR-0054](../adr/0054-upstream-session-pooling.md)).

## Identity
One `User` per human, provisioned from OIDC `(issuer, sub)` regardless of entry path (admin UI or connector authorize
flow). The bundlemcp user id is the `sub` everywhere: introspection, metering, audit, `X-MCP-User`. The IdP subject
travels beside it — to the metering hook and in introspection — and can replace it in `X-MCP-User`, for an application
layer keyed on the IdP. Machine callers are API keys (`endpoint` vs `service` kind).

## Typing
Pydantic v2 everywhere: plain Pydantic entities, SQLModel row classes in the persistence adapter
([ADR-0034](../adr/0034-pydantic-entities-and-row-classes.md)), DTOs in `application/schemas/` → OpenAPI → generated
TS client. Validation at every boundary; no hand-written duplicate shapes
([ADR-0003](../adr/0003-sqlmodel-pydantic-first.md)).

## Security
Threat model + controls centralized in [security spec](../../openspec/specs/security/spec.md): one egress-policy layer
for all admin-supplied URLs (SSRF), CORS/CSRF rules, size limits, DCR quotas, secret redaction (testable), tokens hashed
/ upstream tokens and client secrets encrypted with rotatable keys, moved under the newest key on read and by a leased
background pass that reports when an old key may be dropped ([DEP-9](../../openspec/specs/deployment/spec.md)).

## Error handling
Structured MCP errors to clients; no silent degradation — partial `tools/list` responses increment a dedicated metric
([OPS-11](../../openspec/specs/operations/spec.md)); middleware never swallows errors
([PROT-28](../../openspec/specs/protocol/spec.md)); upstream session loss is retried once, then surfaced
([SES-7](../../openspec/specs/sessions/spec.md)) — a `tools/call` only when the upstream cannot have run it (a 404 for
its session, or a connection that failed before sending).

## Observability
Structured JSON logs (redacted) on standard error, each line of a request carrying its `request_id` (returned as
`X-Request-Id`), the derived client IP, endpoint, session and caller; `/healthz` and a `/readyz` that reports each check
(Postgres, Valkey, schema at the shipped head); optional OpenTelemetry tracing, loaded only when an exporter is
configured ([ADR-0051](../adr/0051-request-context-readiness-report-and-optional-tracing.md)); Prometheus metrics on
`/metrics`, per replica, behind the management credentials, with a closed label set
([ADR-0052](../adr/0052-per-replica-prometheus-metrics-with-a-closed-label-set.md)); per-call audit records in Postgres
as the billing reconciliation source, each carrying the invocation's idempotency key, written in retried batches with
every loss named by that key, and purged after `audit_retention_days`
([ADR-0053](../adr/0053-audit-durability-and-the-idempotency-key-join.md),
[OPS-7](../../openspec/specs/operations/spec.md)).

## Configuration
Deploy-time: `BUNDLEMCP_*` env via pydantic-settings. Runtime-tunable: the `config_entries` table, its legal keys
declared once in `domain/config/config_registry.py`, editable in the UI and propagated via invalidation events
(timeouts, session lifetime, limits).

## Testing
Hermetic unit suite gates every change (ARC-14); integration suite proves the architecture's promises:
restart-under-load, two-replica round-robin, upstream-restart recovery, propagation budget, OAuth happy path (SES-12,
SES-19, AUTH-9); tests cite requirement IDs.
