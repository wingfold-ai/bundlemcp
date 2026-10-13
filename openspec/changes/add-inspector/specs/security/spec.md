## MODIFIED Requirements

### Requirement: SEC-1 One egress policy for gateway-initiated HTTP
All gateway-initiated HTTP to admin-supplied URLs (server probes [UPS-2](../upstreams/spec.md),
server inspection [UPS-11](../upstreams/spec.md), live tool calls, upstream OAuth discovery
[UPS-25](../upstreams/spec.md), inspector ad-hoc targets [UI-8](../admin-ui/spec.md)) MUST go
through one egress policy layer. The policy also covers every URL a remote party names along the way — the
authorization server a protected-resource document points at, the token endpoint its metadata names, a client's
metadata document ([AUTH-13](../auth/spec.md)) — and the operator-configured identity provider
([AUTH-15](../auth/spec.md)); see
[ADR-0032](../../../docs/adr/0032-egress-policy-scope.md).

#### Scenario: Remote-named metadata address is refused before fetch
- **GIVEN** an upstream whose protected-resource document names an authorization server at `http://169.254.169.254/`
- **WHEN** the gateway runs upstream OAuth discovery
- **THEN** the authorization server URL is refused by the egress policy and never fetched

#### Scenario: Client secret only goes where egress allows
- **GIVEN** upstream OAuth metadata whose `token_endpoint` resolves to a blocked address
- **WHEN** the gateway would exchange a code or client credentials
- **THEN** no request carrying the client secret is sent

#### Scenario: Identity provider URLs are checked
- **WHEN** the configured OIDC issuer's discovery or JWKS URL resolves to a blocked address
- **THEN** the gateway refuses to fetch it

#### Scenario: Inspector ad-hoc target is checked
- **WHEN** an admin points the inspector at an ad-hoc URL that resolves to `169.254.169.254`
- **THEN** the egress policy refuses it, nothing is sent, and the inspector reports the denial
