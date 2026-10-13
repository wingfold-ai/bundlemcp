## MODIFIED Requirements

### Requirement: EP-3a OAuth audience binding
OAuth bearers MUST be accepted only when the token's audience matches this endpoint
([AUTH-10](../../../../specs/auth/spec.md)). A presented bearer that is refused — its audience is another
endpoint, or it is expired, revoked or unknown — MUST be answered 401 with
`WWW-Authenticate: Bearer error="invalid_token"` alongside this endpoint's `resource_metadata`, prompting the client to
re-authorize for this endpoint. A request that carries no credentials at all receives the challenge without an error
code (RFC 6750 §3.1). The response never says which of the refusal reasons applied.

#### Scenario: Token issued for another endpoint is refused
- **GIVEN** an access token issued for endpoint `ep1`
- **WHEN** the client presents it at `/ep2/mcp`
- **THEN** the gateway answers 401 with `WWW-Authenticate: Bearer error="invalid_token"` and the `resource_metadata`
  of `ep2`

#### Scenario: Expired or revoked token is refused as invalid
- **WHEN** a client presents an expired or revoked access token at the endpoint it was issued for
- **THEN** the gateway answers 401 with `error="invalid_token"` in the `WWW-Authenticate` challenge

#### Scenario: No credentials keeps the plain challenge
- **WHEN** a client calls an OAuth endpoint without an `Authorization` header
- **THEN** the gateway answers 401 with a `WWW-Authenticate` challenge carrying `resource_metadata` and no `error`
