# ADR-0013: Service-key auth first; admin OIDC sessions land with the UI phase

**Status:** accepted · **Date:** 2026-07-02

> **Update (2026-07-02, milestone 2):** admin OIDC sessions shipped earlier than this ADR anticipated — the OAuth server
> milestone pulled in the OIDC login flow, so the management API now accepts an admin session cookie **or** a service
> key (co-equal). Service keys remain first-class; this ADR is not superseded, only its "later" timing note is
> overtaken. See
> [ADR-0014](0014-gateway-rendered-oauth-authlib.md).

## Context

API-2 (spec 40) requires the management API to accept **either** an admin browser session (OIDC, spec 21) **or** a
service API key. Implementation is staged backend-first (UI deferred by the user's direction), so there is no browser to
log in from yet.

## Decision drivers

- Unblocks the registrar/automation use case (API-4) immediately — the integration the application layer actually needs
  first.
- Avoids building the OIDC browser flow twice (it needs consent pages and the web origin anyway).

## Decision

Phase 1 ships the management API with **service-kind API keys only** (`require_service_auth`), plus
`BUNDLEMCP_INITIAL_SERVICE_KEY` to provision the first key on first boot (BOOT-3 pattern). The OIDC admin-session path
(spec 21) is added together with the Nuxt UI, extending the same dependency — route signatures don't change.

Endpoint OAuth (spec 20, claude profile) is likewise still to be built: endpoints configured `oauth`-only currently
return the 401 challenge, which is the spec-correct behavior for an unauthenticated request.

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- Full management surface usable headlessly from day one.

### Trade-offs

- claude-profile endpoints are not connectable until spec 20 ships — the next major backend milestone.
- `_authenticate` in the endpoint edge has an explicit oauth-pending seam that must be filled, not forgotten (tracked by
  OAS-9's required integration test).

