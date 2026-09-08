# ADR-0010: Single shared workspace — no multi-tenancy in bundlemcp

**Status:** accepted · **Date:** 2026-07-02

## Context

metamcp gives every resource a nullable owner (`user_id`) with public/private
semantics enforced on each access — multi-user ownership inside the gateway.
ultra-mcp, the multi-tenant consumer, builds its own tenanting (Keycloak
realms, entitlements) *around* the gateway and registers servers as public
anyway.

## Decision drivers

- Tenanting is the application layer's concern; duplicating it in the
  gateway doubled metamcp's auth-check surface for little value here.
- Deleting ownership removed a whole class of access-control code and UI.

## Decision

bundlemcp is a **single shared workspace**: every admin sees and manages all
servers/bundles/endpoints/keys. No ownership columns, no per-resource ACLs
([spec/README](../../spec/README.md) decision log;
[spec/02](../../spec/02-domain-model.md)). Non-admin users exist only as
endpoint consumers (OAuth identities, upstream-token owners).

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- Simpler domain model, API, and UI; fewer authorization bugs possible.

### Trade-offs

- bundlemcp alone cannot host mutually-distrusting admin groups on one
  instance — run one instance per team, or put an application layer in
  front. Revisit only with new evidence (per the decision-log rule).

