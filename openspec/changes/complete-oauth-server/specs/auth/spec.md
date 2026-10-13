## MODIFIED Requirements

### Requirement: AUTH-5 Introspection
`POST /oauth/introspect` (RFC 7662) SHALL return `active`, `sub` (bundlemcp user id, see
[architecture](../architecture/spec.md) `User`), `client_id`, `exp`, `scope`, and for a user's token the
RFC 7662 §2.2 extension members `oidc_iss` and `oidc_sub` — the issuer and subject of the IdP that authenticated the
user, which stay stable where the gateway's user id does not. Callable by upstream services; protected against
anonymous fishing: the caller MUST present either a valid `service`-kind API key
([AUTH-23](../auth/spec.md)), as a bearer token, in `X-API-Key`, or as the RFC 7662 HTTP-Basic client
secret, or the client credentials (HTTP Basic `client_id`/`client_secret`) of a confidential client an admin has
authorised for introspection. A registered client that has not been so authorised is refused like an anonymous caller,
because dynamic client registration is open to anyone. Gateway **API keys** presented as the introspected token are
reported as `active` with `sub` `api_key:<id>` ([AUTH-29](../auth/spec.md) identity format)
and neither `oidc_iss` nor `oidc_sub`, so introspecting upstreams
([AUTH-30](../auth/spec.md)) can serve api_key-authenticated callers and tool discovery of
such upstreams can authenticate via a static `authorization` header. A **delegated token**
([AUTH-32](../auth/spec.md)) is reported `active` with its audience server's URL as `aud`,
`token_use` `delegated`, and the endpoint it was issued through as `act.sub`; one issued for a user also carries that
user's `oidc_iss` and `oidc_sub`.

#### Scenario: A user's token is introspected
- **WHEN** a service-key holder introspects a live access token issued to a user
- **THEN** the response is `active: true` with the user's id as `sub`, the `client_id`, `exp`, `scope`, the endpoint
  audience, `oidc_iss` and `oidc_sub`

#### Scenario: Anonymous or endpoint-key introspection is refused
- **WHEN** introspection is called without credentials, or with an `endpoint`-kind API key
- **THEN** the gateway answers 401 and reveals nothing about the token

#### Scenario: An API key is introspected
- **WHEN** a service-key holder introspects an active gateway API key
- **THEN** the response is `active: true` with `sub` `api_key:<id>` and no `oidc_iss` or `oidc_sub`

#### Scenario: An authorised client introspects with its credentials
- **GIVEN** a confidential client an admin has authorised for introspection
- **WHEN** it calls introspection with its `client_id` and `client_secret` as HTTP Basic
- **THEN** the response reports the token as it would to a service-key holder

#### Scenario: A merely registered client is refused
- **GIVEN** a confidential client obtained through dynamic registration and not authorised for introspection
- **WHEN** it calls introspection with its valid client credentials
- **THEN** the gateway answers 401 and reveals nothing about the token

### Requirement: AUTH-9 End-to-end integration test
The claude.ai happy path MUST be covered by an integration test against the compose stack and its real IdP: register
→ authorize (OIDC login and consent) → code → token → MCP initialize → tools/list → tools/call → refresh →
introspect.

#### Scenario: Happy path against the compose stack
- **WHEN** the integration suite runs against the compose stack
- **THEN** a dynamically registered client completes the authorize flow through the IdP login, lists tools on an
  OAuth endpoint with its token, calls one of them successfully, refreshes, and introspects the refreshed token as
  active with its IdP subject

### Requirement: AUTH-10 Endpoint-bound tokens (RFC 8707)
The authorize request SHALL carry a `resource` parameter identifying the target endpoint (its canonical
`/{endpoint_name}/mcp` URL); issued codes and tokens are bound to that endpoint as **audience** (the access token's
endpoint, [architecture](../architecture/spec.md)) and are accepted **only there**
([EP-3a](../endpoints/spec.md)). An authorize request without `resource`, or whose `resource` is not a
gateway endpoint, is refused with `invalid_target`; a token is never valid across endpoints. The token endpoint SHALL
accept a `resource` parameter for both the authorization-code and the refresh grant: when present it MUST name the
audience of the code or refresh token being redeemed, and any other value is refused with `invalid_target` and issues
nothing. Without it, tokens issued at the token endpoint inherit the audience of the code or refresh token they come
from. Introspection (AUTH-5) reports the audience.

#### Scenario: Token is accepted only at its endpoint
- **WHEN** a token issued for endpoint `ep1` is presented at endpoint `ep2`
- **THEN** `ep2` answers 401 with its own challenge carrying `error="invalid_token"`

#### Scenario: Missing resource is refused
- **WHEN** an authorize request carries no `resource`, or one that does not name a gateway endpoint
- **THEN** the client is redirected with `error=invalid_target` and no code is issued

#### Scenario: Matching resource at the token endpoint
- **GIVEN** an authorization code issued for endpoint `ep1`
- **WHEN** the client redeems it with `resource` set to the canonical URL of `ep1`
- **THEN** the issued access and refresh tokens are bound to `ep1`

#### Scenario: Mismatched resource at the token endpoint
- **GIVEN** a refresh token bound to endpoint `ep1`
- **WHEN** the client redeems it with `resource` naming endpoint `ep2`, or a URL that is no gateway endpoint
- **THEN** the token endpoint answers 400 `invalid_target` and the refresh token is neither rotated nor revoked

#### Scenario: Token request without resource
- **WHEN** the client redeems an authorization code for `ep1` without a `resource` parameter
- **THEN** the issued tokens are bound to `ep1`

### Requirement: AUTH-11 Consent
The authorize flow SHALL show a consent screen (client name + target endpoint + requested scope) before issuing a code.
Consent is persisted per `(user, client, endpoint)` and skipped while unrevoked. A signed-in user SHALL be able to list
and revoke their own consents (web app + `/api/v1/me/consents`), and admins can revoke any user's consent (UI +
management API); either revocation also revokes tokens issued under it. A user can neither see nor revoke another
user's consent through the self-service routes. Consent pages carry the
[SEC-6](../security/spec.md) hardening headers.

#### Scenario: First authorization shows consent
- **WHEN** a signed-in user authorizes a client for an endpoint for the first time
- **THEN** a consent screen names the client, the endpoint and the scope, and no code is issued until they approve

#### Scenario: Denial reaches the client
- **WHEN** the user denies the consent screen
- **THEN** the browser is redirected to the client's redirect URI with `error=access_denied`

#### Scenario: Stored consent is skipped until revoked
- **WHEN** the same user authorizes the same client for the same endpoint again
- **THEN** no consent screen is shown
- **AND** after an admin revokes that consent, the screen is shown again and tokens issued under it no longer work

#### Scenario: A user revokes their own consent
- **GIVEN** a non-admin user signed in to the web app with an active consent for a client
- **WHEN** they list `GET /api/v1/me/consents` and revoke that consent with `DELETE /api/v1/me/consents/{consent_id}`
- **THEN** the consent is no longer listed, tokens issued under it no longer authenticate, and the next authorize
  shows the consent screen again

#### Scenario: Another user's consent is out of reach
- **WHEN** a signed-in user calls `DELETE /api/v1/me/consents/{consent_id}` with the id of another user's consent
- **THEN** the gateway answers 404 and that consent stays active

#### Scenario: Self-service needs a signed-in user
- **WHEN** `/api/v1/me/consents` is called without an admin-UI session, or with a service API key
- **THEN** the gateway answers 401
