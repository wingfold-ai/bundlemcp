# ADR-0006: OIDC-only admin authentication

**Status:** accepted · **Date:** 2026-07-02

## Context

metamcp ships better-auth with local email/password plus optional OIDC — password hashing, signup toggles, session
plumbing that caused real pain. bundlemcp's first consumer runs Keycloak anyway; standalone users can run any OIDC IdP.

## Decision drivers

- Deletes the entire password/signup attack-and-maintenance surface.
- Matches the boundary: bundlemcp orchestrates auth but does not *be* an IdP.
- One identity per human across admin UI and connector flows (AUTH-16).

## Decision

Humans authenticate **exclusively via an external OIDC provider** ([spec/21](../../openspec/specs/auth/spec.md)).
No local passwords, no signup flow. The dev compose stack ships a lightweight IdP so bundlemcp still "lives by itself".
End users in the endpoint OAuth flow authenticate through the same federation
([spec/20](../../openspec/specs/auth/spec.md) AUTH-3).

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- No credential storage; IdP policies (MFA, lockout) apply for free.

### Trade-offs

- A running IdP is a hard dependency even for toy deployments (mitigated by the bundled dev IdP).
- Role sync depends on login-time re-evaluation (AUTH-17) and deactivation paths (AUTH-20) rather than instant IdP push.

