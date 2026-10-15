## ADDED Requirements

### Requirement: EP-24 Allowed browser origins
Each endpoint SHALL carry `allowed_origins`, the browser origins that may use `/{endpoint}/mcp` from another site. An
entry is an `http` or `https` origin (scheme, host and an optional port, with no path, query or fragment; a trailing
slash is dropped and the scheme and host are compared case-insensitively) or the single wildcard `*`, which allows any
origin and may not be combined with other entries. The list is not authentication: it decides only which web pages may
drive a browser against the endpoint, and the caller is still authenticated by `auth_modes`
([EP-3](../endpoints/spec.md)).

- A request whose `Origin` header is the gateway's own public origin ([DEP-1](../deployment/spec.md)), or matches an
  entry, is served, with CORS for that origin per [SEC-5](../security/spec.md).
- A request carrying any other `Origin` (`null` included, unless the list is `*`) MUST be refused with `403` and a
  JSON-RPC error, after the endpoint is looked up and before the caller is authenticated, and the refusal carries no
  CORS grant.
- A request without an `Origin` header is not affected by the list.
- When a write omits the field, an endpoint whose `auth_modes` is `[none]` gets `[]`, and every other endpoint gets
  `["*"]`. An existing endpoint is given the same default by the upgrade.

#### Scenario: Listed origin is served
- **GIVEN** endpoint `main` with `allowed_origins: ["https://app.example"]`
- **WHEN** a browser on `https://app.example` posts to `/main/mcp` with a valid credential
- **THEN** the request is served and the response carries `Access-Control-Allow-Origin: https://app.example`

#### Scenario: Other origin is refused before authentication
- **GIVEN** endpoint `main` with `allowed_origins: ["https://app.example"]`
- **WHEN** a request to `/main/mcp` carries `Origin: https://evil.example`
- **THEN** the gateway answers `403` with a JSON-RPC error and no `Access-Control-Allow-Origin`, without checking the
  request's credential

#### Scenario: Open endpoint refuses cross-site browsers by default
- **GIVEN** an endpoint created with `auth_modes: [none]` and no `allowed_origins`
- **WHEN** a page on any other origin posts to it
- **THEN** the endpoint reports `allowed_origins: []` and the request is refused with `403`

#### Scenario: Clients without an Origin are unaffected
- **GIVEN** endpoint `main` with `allowed_origins: []`
- **WHEN** a script posts to `/main/mcp` without an `Origin` header and with a valid credential
- **THEN** the request is served as before

#### Scenario: Invalid entries are rejected
- **WHEN** an admin writes an endpoint with `allowed_origins: ["https://app.example/path"]`, `["app.example"]` or
  `["*", "https://app.example"]`
- **THEN** the management API rejects the write with a validation error naming the entry

#### Scenario: Upgrade keeps today's behaviour for authenticated endpoints
- **GIVEN** a database with an `oauth` endpoint and a `none` endpoint
- **WHEN** the database is upgraded
- **THEN** the `oauth` endpoint reports `allowed_origins: ["*"]` and the `none` endpoint `[]`
