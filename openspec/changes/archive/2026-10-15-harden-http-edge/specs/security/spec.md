## MODIFIED Requirements

### Requirement: SEC-2 Default egress policy
Default egress policy: **block link-local/metadata ranges** (`169.254.0.0/16`, `fe80::/10`, `fd00:ec2::254/128` —
cloud metadata endpoints), the gateway's own loopback (`127.0.0.0/8`, `::1`) and the unspecified addresses that reach
it (`0.0.0.0/8`, `::`); **allow private RFC 1918 ranges** (compose-network upstreams are the primary use case).
An IPv4-mapped IPv6 address is judged as the IPv4 address it maps. Operators can tighten
(`BUNDLEMCP_EGRESS_DENY_CIDRS`) or extend (`BUNDLEMCP_EGRESS_ALLOW_CIDRS`, evaluated first and winning over the
built-in blocks). Only `http`/`https` URLs with a host are allowed. The policy MUST be enforced on the **resolved
address at connect time** — the address the connection actually dials, never a separate earlier resolution — so a
DNS answer that changes between check and connect (DNS rebinding) cannot reach a blocked address. It applies to every
connection, including each hop of a followed redirect. A host that does not resolve is refused.

#### Scenario: Metadata address is blocked
- **WHEN** a server URL resolves to `169.254.169.254`
- **THEN** the egress policy refuses it

#### Scenario: Private network is allowed
- **WHEN** a server URL resolves to `10.0.0.5`
- **THEN** the egress policy allows it

#### Scenario: Explicit allow wins
- **GIVEN** `BUNDLEMCP_EGRESS_ALLOW_CIDRS` contains `127.0.0.0/8`
- **WHEN** a URL resolves to `127.0.0.1`
- **THEN** the egress policy allows it

#### Scenario: Operator deny range
- **GIVEN** `BUNDLEMCP_EGRESS_DENY_CIDRS` contains `10.1.0.0/16`
- **WHEN** a URL resolves to `10.1.2.3`
- **THEN** the egress policy refuses it

#### Scenario: DNS rebinding between check and connect
- **GIVEN** a hostname that resolves to `10.0.0.5` on its first lookup and to `169.254.169.254` on every later lookup
- **WHEN** the gateway opens a connection to it
- **THEN** no connection to `169.254.169.254` is made, and the request fails with an egress denial

#### Scenario: Redirect to a blocked address
- **WHEN** an upstream answers with a redirect that is followed to a host resolving to a blocked address
- **THEN** the redirected connection is refused by the egress policy and the denial is logged

#### Scenario: IPv6 and mapped forms are covered
- **WHEN** a URL resolves to `fd00:ec2::254`, to `::ffff:169.254.169.254`, or to `0.0.0.0`
- **THEN** the egress policy refuses it

### Requirement: SEC-7 Request body size limit
`/{endpoint}/mcp` and `/api/v1` MUST reject a request body larger than the request limit (runtime-configurable,
default 4 MiB) with `413 Payload Too Large`, before the body is parsed and before any database connection is taken.
A declared `Content-Length` above the limit is refused before the body is read; a body without one (chunked) is
refused as soon as the bytes read exceed the limit. The 413 carries a structured body: a JSON-RPC error on MCP
routes, the API's error object on `/api/v1`. A single upstream response message larger than the upstream response cap
(runtime-configurable, default 16 MiB) is abandoned and answered to the MCP client as a structured error, so one tool
result cannot exhaust a replica's memory. Either limit accepts values from 64 KiB to 64 MiB.

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

## ADDED Requirements

### Requirement: SEC-5 MCP endpoint CORS
MCP endpoints (`/{endpoint}/mcp`) SHALL answer with permissive CORS so browser-based MCP clients work:
`Access-Control-Allow-Origin` reflects the request's `Origin`, credentials are never allowed (authentication is
header-based), preflight requests are answered for the methods and request headers the MCP transport uses, and
`Mcp-Session-Id` and `WWW-Authenticate` are exposed via `Access-Control-Expose-Headers`. MCP endpoints MUST NOT
authenticate a caller by cookie. The management API keeps its own allow-list policy (SEC-4).

#### Scenario: Browser client on another origin
- **WHEN** a request to `/main/mcp` carries `Origin: https://inspector.example`
- **THEN** the response carries `Access-Control-Allow-Origin: https://inspector.example`, no
  `Access-Control-Allow-Credentials: true`, and exposes `Mcp-Session-Id` and `WWW-Authenticate`

#### Scenario: Preflight is answered
- **WHEN** a browser sends `OPTIONS /main/mcp` with `Access-Control-Request-Method: POST` and
  `Access-Control-Request-Headers: authorization, content-type, mcp-protocol-version`
- **THEN** the gateway answers the preflight allowing that method and those headers, without authenticating it

#### Scenario: Unauthenticated challenge is readable
- **WHEN** a browser client on another origin posts to an OAuth endpoint without a token
- **THEN** the 401 response carries the reflected `Access-Control-Allow-Origin`, so the client can read the
  `WWW-Authenticate` challenge

#### Scenario: Management API stays allow-listed
- **WHEN** a request to `/api/v1/upstreams` carries an `Origin` not in `BUNDLEMCP_WEB_ORIGINS`
- **THEN** the response carries no `Access-Control-Allow-Origin` for it
