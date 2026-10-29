# security Specification

## Purpose

The threat model and the controls the other slices rely on. One egress policy for every request the gateway makes to an
admin-supplied or remotely named URL, and its defaults against SSRF (blocked metadata and loopback ranges, allowed
private networks); CORS and CSRF rules for the management API; hardening of the OAuth browser pages; request size
limits; limits against dynamic client registration abuse; lockout after authentication failures; and the rule that
secrets never appear in logs, responses or audit records.

Feature slices reference these controls instead of re-deriving them.

## Requirements

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

### Requirement: SEC-3 Egress denials are visible
Egress denials MUST be logged (WARN, event `egress.denied`) and surfaced as clear errors in the UI/API; they are not
silent failures. A probe or inspection refused by the policy reports the connection state `egress_denied` with an
explanation naming `BUNDLEMCP_EGRESS_ALLOW_CIDRS`.

#### Scenario: Inspecting a blocked URL
- **WHEN** an admin inspects a server URL that resolves to a blocked range
- **THEN** a WARN `egress.denied` log line is written and the inspection result's connection state is `egress_denied`

### Requirement: SEC-4 Management API CORS and CSRF
Management API (`/api/v1`): the CORS allowlist MUST be exactly the web app's origin(s) (`BUNDLEMCP_WEB_ORIGINS`);
credentials are allowed only for those. State-changing requests authenticated by the admin session cookie MUST be
CSRF-protected: `SameSite=Lax` cookies **plus** Origin/Referer check against the gateway's public origin and the web
origins — an `Origin` must equal an allowed origin exactly, a `Referer` must sit under one; a prefix match would admit
`https://gw.example.com.evil.test` (double-submit token as fallback for non-browser callers is not needed — those use
API keys).

#### Scenario: Allowed web origin may mutate
- **GIVEN** `BUNDLEMCP_WEB_ORIGINS` contains `https://ui.example.com`
- **WHEN** a cookie-authenticated `PUT` arrives with `Origin: https://ui.example.com`
- **THEN** the request is accepted

#### Scenario: Lookalike origin is refused
- **WHEN** a cookie-authenticated mutation arrives with `Origin: https://gw.example.com.evil.test`
- **THEN** it is rejected with `403` "CSRF origin check failed"

#### Scenario: CORS echoes only the configured origin
- **WHEN** a preflight request arrives from an origin not in `BUNDLEMCP_WEB_ORIGINS`
- **THEN** the response carries no `Access-Control-Allow-Origin` for it

### Requirement: SEC-6 OAuth browser page hardening
OAuth browser pages (authorize, consent, upstream connect) MUST carry standard hardening headers: a CSP of
`default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; form-action 'self'`, `X-Frame-Options: DENY`
against clickjacked consent, and `Cache-Control: no-store`. `form-action` is widened on one page only, the consent
page, and only by the redirect URI of the authorization it decides, already validated against the client's
registration ([AUTH-2](../auth/spec.md), [AUTH-13](../auth/spec.md)): browsers apply `form-action` to
the redirect that answers a form post, so without it Approve and Deny could never reach a client on another origin.
The source expression is that URI's scheme, host, port and path, never a wildcard, a bare scheme or another client's
URI; because CSP disregards the path of a redirected request, what it admits in practice is that redirect URI's origin.
A redirect URI that cannot be written as a source expression leaves `form-action 'self'` in place, and the consent
answer is a same-origin page linking to the client instead of a redirect.

#### Scenario: Consent page names exactly this client's redirect URI
- **WHEN** the consent page renders for an authorization with redirect URI `https://claude.ai/api/mcp/auth_callback?x=1`
- **THEN** its CSP `form-action` is `'self' https://claude.ai/api/mcp/auth_callback` and it carries
  `X-Frame-Options: DENY` and `Cache-Control: no-store`

#### Scenario: Unwritable redirect URI keeps form-action self
- **WHEN** the redirect URI cannot be written as a CSP source expression
- **THEN** `form-action` stays `'self'` and the consent answer is a same-origin page linking to the client

#### Scenario: Browser reaches a cross-origin client
- **WHEN** a user approves consent in Chromium for a client whose redirect URI is on another origin
- **THEN** the browser follows the redirect to that client

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

### Requirement: SEC-8 Dynamic client registration abuse limits
Dynamic client registration ([AUTH-2](../auth/spec.md)) MUST be rate-limited per IP (Valkey, shares
[EP-20](../endpoints/spec.md) machinery; limits and allow-list exemption per [AUTH-12](../auth/spec.md))
and capped by a global unapproved-client quota: once `BUNDLEMCP_DCR_MAX_UNUSED_CLIENTS` (default 1000) registered
clients have never obtained a token, further registrations are refused until some are used or purged; stale never-used
registrations are purged with the AUTH-8 job.

#### Scenario: Quota reached
- **GIVEN** `BUNDLEMCP_DCR_MAX_UNUSED_CLIENTS` registered clients that have never obtained a token
- **WHEN** another client registers, even with only allow-listed redirect URIs
- **THEN** the registration is refused with `429`

#### Scenario: A used client frees quota
- **WHEN** one of those clients obtains a token
- **THEN** it no longer counts against the unused-client quota

### Requirement: SEC-9 Auth-failure rate limiting
Authentication failures MUST be rate-limited per client IP per [EP-20](../endpoints/spec.md): after
the configured number of failures within the window, the IP is locked out until the window lapses. Authentication
failures and lockout events SHALL be counted in the exported metrics
([OPS-9](../operations/spec.md)), without the client IP as a label.

#### Scenario: Credential scan is locked out
- **WHEN** one IP sends more failed authentications than the configured limit within the window
- **THEN** its further requests are refused as locked out until the window lapses

#### Scenario: Lockout is visible in metrics
- **GIVEN** an auth-failure limit of N per window
- **WHEN** one IP sends N + 1 failed authentications in one window and `/metrics` is scraped
- **THEN** the auth-failure counter has increased by N + 1 and the lockout counter by at least one
- **AND** no metric line contains the client IP

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

### Requirement: SEC-11 Secret-bearing export
An export with `?include_secrets=true` ([MGMT-18](../management/spec.md)) MUST be refused (`403`) unless the caller
holds an admin session; a service API key cannot obtain secret values. Every such export MUST be recorded in the audit
log ([OPS-18](../operations/spec.md)) with the admin's identity and time, and its body MUST carry an explicit warning
field stating that the document contains credentials. The documentation tells operators to treat the file as a
credential.

#### Scenario: Service key cannot export secrets
- **WHEN** `GET /api/v1/export?include_secrets=true` is called with a service-kind API key
- **THEN** the response is `403` and no secret value is returned

#### Scenario: Admin export with secrets is recorded and flagged
- **WHEN** an admin with a session calls `GET /api/v1/export?include_secrets=true`
- **THEN** the body carries the secret values and a `warning` field saying the document contains credentials, and an
  audit entry names the admin and the time of the export

#### Scenario: Default export needs no special rights
- **WHEN** a service-kind API key calls `GET /api/v1/export` without `include_secrets`
- **THEN** the export is returned with placeholders and without a `warning` field

## Out of scope

- Network-level controls (firewalls, service mesh) — deployment guidance in [deployment](../deployment/spec.md).
- Pen-testing/audit process.

## Notes

Trust model:

| Actor | Trust |
|---|---|
| Admin (OIDC, `is_admin`) | Trusted to configure; NOT trusted to reach arbitrary internal networks through the gateway (SSRF controls still apply) |
| Endpoint caller (OAuth user / API key) | Untrusted; sees only what the endpoint exposes |
| Anonymous (`none`-auth endpoints) | Untrusted; explicitly opted in per endpoint |
| Upstream MCP server | Semi-trusted: receives forwarded identity/headers, but its responses/notifications are validated like external input |
| External OIDC IdP | Trusted for authentication claims |
| Application layer (metering hook, service keys) | Trusted service-to-service |

Requirement IDs SEC-5 (permissive CORS on MCP endpoints) and SEC-11 (secret-bearing export) are reserved for changes
not yet implemented.
