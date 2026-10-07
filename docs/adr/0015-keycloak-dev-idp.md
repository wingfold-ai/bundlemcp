# ADR-0015: Keycloak as the bundled dev IdP

**Status:** accepted · **Date:** 2026-07-02 **Resolves:** spec 21 open question (which dev IdP to ship in compose)

## Context

bundlemcp is OIDC-only for humans ([ADR-0006](0006-oidc-only-admin-auth.md)), so the compose stack must ship *some* IdP
for standalone use and integration testing. Candidates were Keycloak (heavy, production-grade), dex (tiny), or a mock.
Hermetic unit tests already use an in-process fake via the `OidcProvider` seam
([ADR-0014](0014-gateway-rendered-oauth-authlib.md)), so this choice only governs the *integration* IdP.

## Decision drivers

- **Parity with the application layer**, which runs Keycloak in production — the integration suite exercises exactly the
  federation bundlemcp will deploy against (claim shapes, login form, logout semantics), catching drift a mock would
  hide.
- Realm import makes the dev setup reproducible and versioned.

## Decision

The `deploy/docker-compose.yml` stack ships **Keycloak** (`start-dev --import-realm`) with
`deploy/keycloak/bundlemcp-realm.json` (realm `bundlemcp`, a confidential gateway client, a demo admin user). The OAS-9
integration test drives Keycloak's real login form end to end.

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- Integration tests prove the real federation, not an approximation.

### Trade-offs

- Heavier compose stack (~1 GB image, slower first boot) — acceptable for a dev/CI dependency; the hermetic unit suite
  stays Docker-free and fast.
- If a lighter default is wanted later, the `OidcProvider` seam and realm file make swapping in dex a small, isolated
  change (revisit with evidence).

