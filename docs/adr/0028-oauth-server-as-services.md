# ADR-0028: The OAuth server is services with grant strategies; browser state is typed and single-use

**Status:** accepted · **Date:** 2026-09-03 · **Amended by:**
[ADR-0036](0036-oauth-slice-decomposition-and-shared-contracts.md) · **Amends:**
[ADR-0014](0014-gateway-rendered-oauth-authlib.md), [ADR-0017](0017-upstream-oauth-encryption.md),
[ADR-0026](0026-controllers.md)

## Context

The "routers are thin" rule of ADR-0019 was enforced for `api/` and exempt in practice for `oauth/`. Client
authentication, PKCE, both grants, refresh rotation, introspection, revocation and the purge loop lived in one route
module; consent and user provisioning in two others. The state each browser round trip needs (pending consent, OIDC
login, upstream connect) was three hand-built blobs in Valkey with three copies of get, delete and check-None.
`UpstreamTokenStore` did three jobs in 258 lines and returned dicts.

## Decision drivers

- A grant per class is the shape the protocol has; a new grant is a new class, not a new branch.
- Round-trip state that is typed and single-use cannot be replayed or misparsed, and the three flows share one
  implementation.
- A class per job in the token store makes the single-flight refresh testable without the connect flow.

## Decision

- **Services in `services/oauth_server/`.** `OAuthTokenService` authenticates the client and runs the requested
  `TokenGrant`; `AuthorizationCodeGrant` and `RefreshTokenGrant` implement that protocol, sharing a `TokenIssuer`.
  `AuthorizationService` validates an authorization request, answers the consent question and issues codes;
  `TokenIntrospectionService`, `ClientRegistrationService`, `UserProvisioningService` and `TokenPurgeService` carry the
  rest. Failures are `OAuthError` (rendered in the protocol's shape once, by one exception handler) or
  `AuthorizationRedirectError` (delivered to the verified redirect URI).
- **Controllers in `oauth/`** parse forms and cookies, call one service method and render. `TokenPurger` schedules the
  purge service from the composition root. The RFC response bodies are models in `schemas/oauth/`.
- **`SingleUseState[T]`** (`store/single_use_state.py`) parks a typed record under an unguessable token and deletes it
  on read. `PendingAuthorization`, `OidcLoginState` and `UpstreamConnectState` are its three records.
- **PKCE lives in `crypto/`** as `PkcePair` and `pkce_verifies`, shared by the authorization server and the upstream
  connect flow.
- **The upstream token store is three classes behind one facade.** `UpstreamTokenRepository` (rows and the cipher),
  `UpstreamConnectFlow` (PKCE, authorize URL, exchange) and `UpstreamTokenRefresher` (single-flight refresh) compose
  into `UpstreamTokenStore`, whose public methods are unchanged.

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- `oauth/` follows the same controller-and-service shape as `api/`; the exemption is gone.
- The public OAuth surface is unchanged; the package README was rewritten to match the new layout.

### Trade-offs

- A public client's registration response and an inactive introspection omit null fields through
  `response_model_exclude_none`, which the RFC shapes require and the models do not express on their own.

