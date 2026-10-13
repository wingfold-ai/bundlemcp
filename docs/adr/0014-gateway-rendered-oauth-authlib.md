# ADR-0014: Gateway-rendered auth pages, authlib as OIDC RP, direct-DB token validation

**Status:** accepted · **Date:** 2026-07-02 · **Amended by:** [ADR-0028](0028-oauth-server-as-services.md),
[ADR-0031](0031-joserfc-id-token-validation.md) (joserfc replaces authlib, which is no longer a dependency),
[ADR-0036](0036-oauth-slice-decomposition-and-shared-contracts.md)

## Context

Milestone 2 built the OAuth 2.1 server (spec 20) and OIDC admin login (spec 21) backend-first, before the Nuxt UI
exists. Three implementation decisions followed: where the consent/login pages render, how the gateway talks to the
external IdP, and how issued bearers are validated on the hot path.

## Decision drivers

- Unblocks claude.ai connection now, independent of the frontend timeline.
- Server-rendered consent is the standard, dependency-light approach (metamcp did the same) and keeps the
  security-sensitive page in one trust domain.
- Direct DB validation removes per-request latency and a self-dependency.

## Decision

- **Gateway-rendered pages:** the consent screen (and login redirect handling) are minimal server-side Jinja templates
  served by the gateway itself (`oauth/templates/`, `oauth/authorize.py`), under SEC-6 hardening headers (CSP,
  `X-Frame-Options: DENY`). No Nuxt dependency; the UI later only manages/revokes consents via the API.
- **authlib as the OIDC relying party:** `AuthlibOidcProvider` behind an `OidcProvider` Protocol (`oauth/oidc.py`) —
  discovery, code exchange, id_token/JWKS validation. The Protocol lets hermetic tests inject a fake issuer instead of
  running Keycloak (ARC-14).
- **Direct-DB token validation (AUTH-7):** endpoint bearers are validated by a hashed lookup in `oauth_access_tokens`
  with an audience check, **not** by an HTTP self-call to `/oauth/introspect` — explicitly avoiding metamcp's
  introspect-yourself-over-HTTP anti-pattern.

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- The whole OAuth + OIDC flow is testable and deployable without the UI.
- `OidcProvider` seam gives clean hermetic tests and room for non-Keycloak IdPs.

### Trade-offs

- The gateway owns a little HTML/templating — a non-Nuxt surface to keep styled consistently later.
- `AuthlibOidcProvider.authorize_url` needs discovery metadata preloaded at startup (async), a small lifecycle wrinkle
  documented in the provider.

