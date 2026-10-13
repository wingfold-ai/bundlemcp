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
All gateway-initiated HTTP to admin-supplied URLs (server probes [UPS-2](../upstreams/spec.md), server
inspection [UPS-11](../upstreams/spec.md), live tool calls, upstream OAuth discovery
[UPS-25](../upstreams/spec.md)) MUST go through one egress policy layer. The policy also covers every URL a remote
party names along the way — the authorization server a protected-resource document points at, the token endpoint its
metadata names, a client's metadata document ([AUTH-13](../auth/spec.md)) — and the operator-configured identity
provider ([AUTH-15](../auth/spec.md)); see [ADR-0032](../../../docs/adr/0032-egress-policy-scope.md).

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

### Requirement: SEC-2 Default egress policy
Default egress policy: **block link-local/metadata ranges** (`169.254.0.0/16`, `fe80::/10` — cloud metadata endpoints)
and the gateway's own loopback (`127.0.0.0/8`, `::1`); **allow private RFC 1918 ranges** (compose-network upstreams are
the primary use case). Operators can tighten (`BUNDLEMCP_EGRESS_DENY_CIDRS`) or extend (`BUNDLEMCP_EGRESS_ALLOW_CIDRS`,
evaluated first and winning over the built-in blocks). Only `http`/`https` URLs with a host are allowed. The policy
MUST be judged on **every address the hostname resolves to** (not just the hostname), as a pre-flight check before the
request is made; a host that does not resolve is refused.

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
`/{endpoint}/mcp` MUST reject a request whose declared `Content-Length` exceeds 4 MiB with `413 Payload Too Large`,
before the body is parsed and before any database connection is taken.

#### Scenario: Oversized MCP request
- **WHEN** a client POSTs to `/{endpoint}/mcp` with `Content-Length` above 4 MiB
- **THEN** the gateway answers `413` without admitting the request to the database

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
Authentication failures MUST be rate-limited per client IP per [EP-20](../endpoints/spec.md): after the configured
number of failures within the window, the IP is locked out until the window lapses.

#### Scenario: Credential scan is locked out
- **WHEN** one IP sends more failed authentications than the configured limit within the window
- **THEN** its further requests are refused as locked out until the window lapses

### Requirement: SEC-10 Secrets stay secret
Secret values (API keys, tokens, static/forwarded header values, client secrets) MUST NOT appear in logs, audit
records, API responses (beyond one-time display at creation), or error messages. Server reads return static header
names only; upstream OAuth status never returns the client secret; stored upstream tokens and client secrets are
ciphertext.

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
