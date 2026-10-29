# Spec Delta

## MODIFIED Requirements

### Requirement: SEC-7 Request body size limit
`/{endpoint}/mcp` and `/api/v1` MUST reject a request body larger than the request limit (runtime-configurable,
default 4 MiB) with `413 Payload Too Large`, before the body is parsed and before any database connection is taken.
A declared `Content-Length` above the limit is refused before the body is read; a body without one (chunked) is
refused as soon as the bytes read exceed the limit. The 413 carries a structured body: a JSON-RPC error on MCP
routes, the API's error object on `/api/v1`. A single upstream response message larger than the upstream response cap
(runtime-configurable, default 16 MiB) is abandoned and answered to the MCP client as a structured error, so one tool
result cannot exhaust a replica's memory. Either limit accepts values from 64 KiB to 64 MiB.

Every path under `/oauth/` is reachable before anyone signs in, so it MUST be held to a fixed, smaller limit of 64 KiB
in the same way: a declared or streamed body over it is refused with `413` before it is parsed, and the 413 carries
an OAuth error object (`error` `invalid_request` with an `error_description`). This limit is not configurable and does
not follow the runtime request limit.

#### Scenario: Oversized MCP request
- **WHEN** a client POSTs to `/{endpoint}/mcp` with `Content-Length` above the request limit
- **THEN** the gateway answers `413` with a JSON-RPC error body, without admitting the request to the database

#### Scenario: Chunked body over the limit
- **WHEN** a client streams a body without `Content-Length` to `/{endpoint}/mcp` or `/api/v1` that grows past the
  request limit
- **THEN** the gateway stops reading and answers `413`, holding at most the limit plus one read chunk in memory

#### Scenario: Management API request over the limit
- **WHEN** a client PUTs a body larger than the request limit to `/api/v1/bundles/main`
- **THEN** the gateway answers `413` with the API's error object and changes nothing

#### Scenario: Limit changed at runtime
- **GIVEN** an admin lowers the request limit to 1 MiB through the runtime configuration
- **WHEN** a 1.5 MiB request then arrives at any replica
- **THEN** it is refused with `413` once the configuration change has propagated

#### Scenario: Oversized upstream response
- **WHEN** an upstream answers a `tools/call` with a single message larger than the upstream response cap
- **THEN** the caller receives a structured MCP error saying the upstream response was too large, and the replica does
  not buffer the rest of the message

#### Scenario: Oversized registration body
- **WHEN** a client POSTs a 100 KiB body to `/oauth/register`, with or without `Content-Length`
- **THEN** the gateway answers `413` with `error` `invalid_request`, without parsing the body and without registering
  a client

#### Scenario: OAuth limit ignores the runtime request limit
- **GIVEN** an admin raises the runtime request limit to 16 MiB
- **WHEN** a client POSTs a 100 KiB form body to `/oauth/token`
- **THEN** the gateway still answers `413`

### Requirement: SEC-10 Secrets stay secret
Secret values (API keys, tokens, static/forwarded header values, client secrets) MUST NOT appear in logs, metric labels,
audit records, API responses (beyond one-time display at creation), or error messages. Server reads return static
header names only; upstream OAuth status never returns the client secret; stored upstream tokens, client secrets and
static header values are ciphertext whenever an encryption key is configured ([ARC-18](../architecture/spec.md)). A
unit-test helper SHALL assert redaction on representative paths: logs, metrics output and error bodies.

#### Scenario: Header values are withheld
- **GIVEN** a server registered with a static `Authorization` header
- **WHEN** an admin reads the server through the management API
- **THEN** the response lists `static_header_names` and no header value

#### Scenario: API key value is shown once
- **WHEN** an API key is created
- **THEN** the creation response carries the key value, and every later read carries only its prefix and metadata

#### Scenario: Upstream OAuth status omits the secret
- **GIVEN** a server with a stored upstream OAuth client secret
- **WHEN** the upstream OAuth status is read
- **THEN** the response does not contain the secret

#### Scenario: Metric labels carry no secret or caller identity
- **GIVEN** tool calls made with an API key, an OAuth bearer and a forwarded identity header
- **WHEN** `/metrics` is scraped
- **THEN** the redaction helper finds none of the key value, the bearer, the header value, the user's `sub` or the API
  key id in the output

#### Scenario: Redaction helper covers logs and error bodies
- **WHEN** a request with a bad API key is rejected and the captured log records and the error body are passed to the
  redaction helper together with the presented key
- **THEN** the helper reports no occurrence of the key value

#### Scenario: Static header values are ciphertext in the database
- **GIVEN** a gateway with an encryption key, and a server registered with static header `Authorization: Bearer s3cret`
- **WHEN** the `mcp_servers` row is read directly from Postgres
- **THEN** neither `s3cret` nor `Bearer s3cret` appears in any of its columns
