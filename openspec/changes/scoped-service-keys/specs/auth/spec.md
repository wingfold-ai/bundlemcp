# Spec Delta

## ADDED Requirements

### Requirement: AUTH-40 Scopes of a service key
A service key SHALL carry an optional list of **scopes**, each one of `introspect`, `read`, `bundles:write`,
`endpoints:write`, `upstreams:write`, `keys:manage` and `mcp`. A service key without scopes SHALL keep every right a
service key has. A scoped service key SHALL be allowed only what its scopes open: `introspect` the introspection route
([AUTH-5](../auth/spec.md)), `mcp` the authentication of MCP calls on endpoints with `api_key` in their `auth_modes`,
and the others the management routes that declare them ([MGMT-23](../management/spec.md)). A scoped key without `mcp`
SHALL NOT authenticate an MCP call. An endpoint key SHALL take no scopes, and an unknown scope SHALL be refused, with
422 from the API. Scopes SHALL be shown when a key is read or listed. A scoped caller holding `keys:manage` SHALL
create, activate, deactivate or delete only service keys that have scopes, all of which the caller holds itself;
anything else is answered 403.

#### Scenario: Unscoped service key keeps every right
- **GIVEN** a service key without scopes
- **WHEN** it calls any management route, the introspection route, or an `api_key` endpoint
- **THEN** it is accepted as before

#### Scenario: Scoped key outside its scopes
- **GIVEN** a service key scoped to `read`
- **WHEN** it calls `PUT /api/v1/bundles/x`
- **THEN** the gateway answers 403 and changes nothing

#### Scenario: No tool calls without mcp
- **GIVEN** a service key scoped to `introspect` and `read`
- **WHEN** it is presented at an endpoint with `api_key` in its `auth_modes`
- **THEN** the request is not authenticated by that key

#### Scenario: No escalation through keys:manage
- **GIVEN** a service key scoped to `keys:manage` and `read`
- **WHEN** it creates a service key without scopes, an endpoint key, or a key scoped to `mcp`
- **THEN** the gateway answers 403 and no key is created
- **AND WHEN** it creates a service key scoped to `read`
- **THEN** the key is created

#### Scenario: Invalid scopes
- **WHEN** an admin creates a key with an unknown scope, or an endpoint key with any scope
- **THEN** the gateway answers 422 and no key is created

## MODIFIED Requirements

### Requirement: AUTH-5 Introspection
`POST /oauth/introspect` (RFC 7662) SHALL return `active`, `sub` (bundlemcp user id, see
[architecture](../architecture/spec.md) `User`), `client_id`, `exp`, `scope`, and for a user's token the RFC 7662 §2.2
extension members `oidc_iss` and `oidc_sub` — the issuer and subject of the IdP that authenticated the user, which stay
stable where the gateway's user id does not. Callable by upstream services; protected against anonymous fishing: the
caller MUST present a valid `service`-kind API key ([AUTH-23](../auth/spec.md)) without scopes or with the `introspect`
scope ([AUTH-40](../auth/spec.md)), as a bearer token, in `X-API-Key`, or as the RFC 7662 HTTP-Basic client secret.
Gateway **API keys** presented as the introspected token are reported as `active` with `sub` `api_key:<id>`
([AUTH-29](../auth/spec.md) identity format) and neither `oidc_iss` nor `oidc_sub`, so introspecting upstreams
([AUTH-30](../auth/spec.md)) can serve api_key-authenticated callers and tool discovery of such upstreams can
authenticate via a static `authorization` header. A scoped service key without the `mcp` scope presented as the
introspected token is reported inactive: it never authenticates a caller. A **delegated token**
([AUTH-32](../auth/spec.md)) is reported `active` with its audience server's URL as `aud`, `token_use` `delegated`, and
the endpoint it was issued through as `act.sub`; one issued for a user also carries that user's `oidc_iss` and
`oidc_sub`.

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

#### Scenario: A key scoped to introspect introspects
- **WHEN** a holder of a service key scoped to `introspect` introspects a live token
- **THEN** the response is the same as for a holder of an unscoped service key

#### Scenario: A scoped key without introspect is refused
- **WHEN** a holder of a service key scoped to `read` calls introspection
- **THEN** the gateway answers 401 and reveals nothing about the token

### Requirement: AUTH-23 Name, scope and kind
Keys SHALL carry a `name`, unique among all keys, an optional **endpoint scope** (list of endpoint ids; empty = all
endpoints), and a **kind**: `endpoint` (can call scoped endpoints) or `service` (can also call the management API,
within its scopes, [AUTH-40](../auth/spec.md)). Creating a key under a name another key already has SHALL be refused
with 409.

#### Scenario: Scoped key outside its scope
- **WHEN** a key scoped to endpoint `a` is presented at endpoint `b`
- **THEN** the request is not authenticated by that key

#### Scenario: Endpoint key at the management API
- **WHEN** an `endpoint`-kind key calls the management API
- **THEN** the gateway answers 403, while a `service`-kind key is accepted

#### Scenario: Duplicate key name
- **GIVEN** a key named `ci` exists
- **WHEN** an admin creates another key named `ci`
- **THEN** the gateway answers 409 and no key is created
