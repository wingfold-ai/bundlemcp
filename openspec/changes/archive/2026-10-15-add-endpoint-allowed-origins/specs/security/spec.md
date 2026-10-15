## MODIFIED Requirements

### Requirement: SEC-5 MCP endpoint CORS
MCP endpoints (`/{endpoint}/mcp`) SHALL answer browser-based MCP clients with CORS according to the endpoint's allowed
origins ([EP-24](../endpoints/spec.md)): for a request whose `Origin` is allowed, `Access-Control-Allow-Origin`
reflects that origin (with `Vary: Origin`), credentials are never allowed (authentication is header-based), preflight
requests are answered for the methods and request headers the MCP transport uses, and `Mcp-Session-Id` and
`WWW-Authenticate` are exposed via `Access-Control-Expose-Headers`. A request or preflight from an origin the endpoint
does not allow is refused with `403` and gets no CORS grant. A response the gateway gives before it has resolved the
endpoint (an unknown endpoint, a body over the size limit) carries no CORS grant. MCP endpoints MUST NOT authenticate a
caller by cookie. The management API keeps its own allow-list policy (SEC-4).

#### Scenario: Browser client on another origin
- **GIVEN** endpoint `main` whose allowed origins include `https://inspector.example` (or are `*`)
- **WHEN** a request to `/main/mcp` carries `Origin: https://inspector.example`
- **THEN** the response carries `Access-Control-Allow-Origin: https://inspector.example`, no
  `Access-Control-Allow-Credentials: true`, and exposes `Mcp-Session-Id` and `WWW-Authenticate`

#### Scenario: Preflight is answered
- **GIVEN** endpoint `main` whose allowed origins include the requesting origin
- **WHEN** a browser sends `OPTIONS /main/mcp` with `Access-Control-Request-Method: POST` and
  `Access-Control-Request-Headers: authorization, content-type, mcp-protocol-version`
- **THEN** the gateway answers the preflight allowing that method and those headers, without authenticating it

#### Scenario: Unauthenticated challenge is readable
- **GIVEN** an OAuth endpoint whose allowed origins include the client's origin
- **WHEN** a browser client on that origin posts to it without a token
- **THEN** the 401 response carries the reflected `Access-Control-Allow-Origin`, so the client can read the
  `WWW-Authenticate` challenge

#### Scenario: Management API stays allow-listed
- **WHEN** a request to `/api/v1/upstreams` carries an `Origin` not in `BUNDLEMCP_WEB_ORIGINS`
- **THEN** the response carries no `Access-Control-Allow-Origin` for it

#### Scenario: Preflight from an origin the endpoint does not allow
- **GIVEN** endpoint `main` with `allowed_origins: []`
- **WHEN** a browser on `https://evil.example` sends a preflight for `/main/mcp`
- **THEN** the gateway answers `403` without any `Access-Control-Allow-*` header, so the browser sends nothing further
