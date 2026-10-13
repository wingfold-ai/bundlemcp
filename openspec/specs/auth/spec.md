# auth Specification

## Purpose

Who may call the gateway, and who the upstreams learn the caller is. The built-in OAuth 2.1 authorization server for MCP
clients (discovery, dynamic and metadata-document client registration, PKCE, consent, endpoint-bound tokens,
introspection and revocation), OIDC-only login for admins and users with roles taken from the identity provider, API
keys for scripts and services, and identity forwarding: selected client headers, the X-MCP-User header and delegated
tokens that tell an upstream who is calling.

Authenticating the gateway to an upstream with the upstream's own OAuth is the upstreams slice.

It merges what were separate specs until 2026-10-13: OAuth server, Admin authentication, API keys, Identity forwarding.

## Requirements

### Requirement: AUTH-1 Discovery
The gateway SHALL serve `/.well-known/oauth-authorization-server` (RFC 8414) and, per endpoint, the RFC 9728
protected-resource metadata at `/.well-known/oauth-protected-resource/{endpoint_name}/mcp`, consistent with the
endpoints' 401 challenges ([EP-3](../endpoints/spec.md)).

#### Scenario: Authorization server metadata is served
- **WHEN** a client fetches `/.well-known/oauth-authorization-server`
- **THEN** the document names the gateway as `issuer` and lists the authorize, token, registration, introspection and
  revocation endpoints under the public base URL

#### Scenario: Protected-resource metadata matches the challenge
- **WHEN** an unauthenticated request to an OAuth endpoint is answered 401
- **THEN** the challenge's `resource_metadata` names the endpoint's protected-resource document
- **AND** that document's `resource` is the endpoint's canonical `/{endpoint_name}/mcp` URL and its authorization
  server is the gateway

### Requirement: AUTH-2 Dynamic Client Registration
The gateway SHALL accept RFC 7591 registration at `POST /oauth/register`: open registration, public clients
(`token_endpoint_auth_method: none`) by default, redirect URIs validated (https or localhost); an `application_type`
sent by the client is accepted and stored. An operator MAY narrow the accepted redirect URIs with an allow-list
(`BUNDLEMCP_DCR_ALLOWED_REDIRECT_URIS`); empty (the default) accepts every URI the rule above accepts. Each entry is
either an exact URI, matched by simple string comparison, or a URI whose leftmost host label is `*`
(`https://*.example.com/oauth/callback`), which matches exactly one DNS label in that position with scheme, port, path
and query unchanged (`a.example.com` matches; `example.com` and `a.b.example.com` do not). `*` is valid nowhere else
and needs at least two host labels after it; a malformed entry refuses startup. The allow-list narrows the
https-or-localhost rule and never widens it. A registration the server cannot honour MUST be refused with HTTP 400 and
the RFC 7591 error code, never the framework's validation shape: an unsupported grant type, response type, auth method
or application type, or a body that is not valid JSON, is `invalid_client_metadata`; a redirect URI that fails the
rule above, or is missing from a configured allow-list, is `invalid_redirect_uri`. The implicit and password grants
stay unsupported: OAuth 2.1 removed them, and MCP clients use the authorization code grant with PKCE. MCP 2026-07-28
deprecates DCR in favour of Client ID Metadata Documents (AUTH-13); it stays supported for clients that have not moved
(ChatGPT, Claude as of 2026-09).

#### Scenario: Public client registers
- **WHEN** a client posts metadata with an https redirect URI and no auth method
- **THEN** the gateway answers 201 with a `client_id` and `token_endpoint_auth_method` `none`
- **AND** an `application_type` the client sent is stored and echoed

#### Scenario: Redirect URI outside the rule is refused
- **WHEN** a client registers a plain-http redirect URI on a non-localhost host, or one missing from a configured
  allow-list
- **THEN** the gateway answers 400 with `error` `invalid_redirect_uri`

#### Scenario: Wildcard allow-list entry matches one label
- **GIVEN** the allow-list entry `https://*.example.com/oauth/callback`
- **WHEN** clients register `https://a.example.com/oauth/callback`, `https://example.com/oauth/callback` and
  `https://a.b.example.com/oauth/callback`
- **THEN** only the first is accepted; the others are refused with `invalid_redirect_uri`

#### Scenario: Unsupported metadata is refused in RFC 7591 shape
- **WHEN** a client registers the `implicit` or `password` grant, or posts a body that is not valid JSON
- **THEN** the gateway answers 400 with `error` `invalid_client_metadata`

### Requirement: AUTH-3 Authorization code + PKCE
`GET /oauth/authorize` SHALL require an authenticated browser session — if absent, redirect into the OIDC login and
return to complete the flow. S256 PKCE is REQUIRED for public clients. Codes are single-use, 10-minute expiry by
default (`authorization_code_lifetime`), bound to client + redirect URI + challenge. The burn is atomic (a
compare-and-set on the stored code), so two redemptions racing on one code yield one token pair.

#### Scenario: Unauthenticated authorize goes through the IdP
- **WHEN** a browser without a gateway session opens a valid authorize URL
- **THEN** it is redirected into the OIDC login and, after login, returns to the authorize flow

#### Scenario: Missing or non-S256 PKCE is refused
- **WHEN** a public client sends an authorize request without a `code_challenge`, or with method `plain`
- **THEN** no code is issued and the client is redirected with an `invalid_request` error

#### Scenario: A code is redeemed once
- **WHEN** the same authorization code is presented to the token endpoint twice, including concurrently
- **THEN** exactly one token pair is issued and the other redemption fails with `invalid_grant`

### Requirement: AUTH-4 Token endpoint
`POST /oauth/token` SHALL support the `authorization_code` and `refresh_token` grants. Access tokens are opaque
(`bmcp_…` prefix), default 1h lifetime; refresh tokens default 7d and are **rotated on every use** (old one revoked). A
refresh token presented again after rotation is treated as stolen: every pair descended from the same authorization
grant (the token *family*) is revoked (RFC 9700 §4.14.2). Lifetimes are runtime-configurable (`Config`:
`access_token_lifetime`, `refresh_token_lifetime`, in seconds) and read when a pair is issued. The grant types a
client registered (AUTH-2) or its metadata document declares (AUTH-13) are honoured: a grant outside that list is
refused with `unauthorized_client`, and so is an authorization request from a client that did not register
`authorization_code`.

#### Scenario: Refresh rotates the pair
- **WHEN** a client redeems its refresh token
- **THEN** it receives a new access and refresh token and the old refresh token no longer works

#### Scenario: Replay of a rotated refresh token revokes the family
- **WHEN** a refresh token that was already rotated is presented again
- **THEN** the request fails with `invalid_grant`
- **AND** every access and refresh token descended from the same authorization grant is revoked

#### Scenario: Unregistered grant is refused
- **WHEN** a client that registered only `authorization_code` presents a `refresh_token` grant
- **THEN** the token endpoint answers `unauthorized_client`

### Requirement: AUTH-5 Introspection
`POST /oauth/introspect` (RFC 7662) SHALL return `active`, `sub` (bundlemcp user id, see
[architecture](../architecture/spec.md) `User`), `client_id`, `exp`, `scope`, and for a user's token the RFC 7662 §2.2
extension members `oidc_iss` and `oidc_sub` — the issuer and subject of the IdP that authenticated the user, which stay
stable where the gateway's user id does not. Callable by upstream services; protected against anonymous fishing: the
caller MUST present a valid `service`-kind API key ([AUTH-23](../auth/spec.md)), as a bearer token, in `X-API-Key`,
or as the RFC 7662 HTTP-Basic client secret. Gateway **API keys** presented as the introspected token are reported as
`active` with `sub` `api_key:<id>` ([AUTH-29](../auth/spec.md) identity format) and neither `oidc_iss`
nor `oidc_sub`, so introspecting upstreams ([AUTH-30](../auth/spec.md)) can serve api_key-authenticated
callers and tool discovery of such upstreams can authenticate via a static `authorization` header. A **delegated
token** ([AUTH-32](../auth/spec.md)) is reported `active` with its audience server's URL as `aud`,
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

### Requirement: AUTH-6 Revocation
The gateway SHALL serve RFC 7009 revocation at `POST /oauth/revoke` for access and refresh tokens. The client
authenticates as at the token endpoint (a public client by `client_id` alone) and may revoke only tokens issued to it;
a token that is unknown or another client's is answered 200 and left alone. Authentication failures count toward the
[EP-20](../endpoints/spec.md) lockout.

#### Scenario: Client revokes its own token
- **WHEN** a client revokes an access or refresh token issued to it
- **THEN** the gateway answers 200 and the token no longer authenticates

#### Scenario: Another client's token is left alone
- **WHEN** a client revokes a token issued to a different client
- **THEN** the gateway answers 200 and the token keeps working

#### Scenario: Failed client authentication is counted
- **WHEN** a revocation request carries client credentials that do not authenticate
- **THEN** the gateway answers 401 and counts the failure toward the per-IP auth lockout

### Requirement: AUTH-7 Direct token validation
Resource-server validation of bearer tokens on endpoints MUST be a **direct database/Redis lookup**, not an HTTP
self-call to the introspection route (metamcp anti-pattern: it introspected itself over HTTP per request).

#### Scenario: Endpoint bearer is checked in-process
- **WHEN** an MCP request carries a gateway access token
- **THEN** the token's digest is looked up in the gateway's own store and no HTTP request is made to
  `/oauth/introspect`

### Requirement: AUTH-8 Hashed storage and purge
Token values MUST be stored hashed ([ARC-18](../architecture/spec.md)); expired codes/tokens are purged by a periodic
job.

#### Scenario: Only digests are persisted
- **WHEN** an authorization code or token pair is issued
- **THEN** the store holds only the SHA-256 digest of each value, never the value itself

#### Scenario: Expired grants are purged
- **WHEN** the periodic purge runs
- **THEN** expired authorization codes and tokens are deleted

### Requirement: AUTH-9 End-to-end integration test
The claude.ai happy path MUST be covered by an integration test against the compose stack and its real IdP: register
→ authorize (OIDC login and consent) → code → token → MCP initialize → tools/list → refresh → introspect.

#### Scenario: Happy path against the compose stack
- **WHEN** the integration suite runs against the compose stack
- **THEN** a dynamically registered client completes the authorize flow through the IdP login, lists tools on an
  OAuth endpoint with its token, refreshes, and introspects the refreshed token as active with its IdP subject

### Requirement: AUTH-10 Endpoint-bound tokens (RFC 8707)
The authorize request SHALL carry a `resource` parameter identifying the target endpoint (its canonical
`/{endpoint_name}/mcp` URL); issued codes and tokens are bound to that endpoint as **audience** (the access token's
endpoint, [architecture](../architecture/spec.md)) and are accepted **only there** ([EP-3a](../endpoints/spec.md)). An
authorize request without `resource`, or whose `resource` is not a gateway endpoint, is refused with `invalid_target`;
a token is never valid across endpoints. Tokens issued at the token endpoint inherit the audience of the code or
refresh token they come from. Introspection (AUTH-5) reports the audience.

#### Scenario: Token is accepted only at its endpoint
- **WHEN** a token issued for endpoint `ep1` is presented at endpoint `ep2`
- **THEN** `ep2` answers 401 with its own challenge

#### Scenario: Missing resource is refused
- **WHEN** an authorize request carries no `resource`, or one that does not name a gateway endpoint
- **THEN** the client is redirected with `error=invalid_target` and no code is issued

### Requirement: AUTH-11 Consent
The authorize flow SHALL show a consent screen (client name + target endpoint + requested scope) before issuing a code.
Consent is persisted per `(user, client, endpoint)` and skipped while unrevoked; admins can revoke a user's consent
(UI + management API), which also revokes tokens issued under it. Consent pages carry the
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

### Requirement: AUTH-12 Registration abuse controls
Dynamic client registration abuse controls SHALL apply per [SEC-8](../security/spec.md). The per-IP limit is
configurable (`BUNDLEMCP_DCR_RATE_LIMIT` registrations per `BUNDLEMCP_DCR_RATE_WINDOW` seconds, default 10 per 3600). A
registration whose redirect URIs are all on a configured allow-list (AUTH-2) is exempt from the per-IP limit — a hosted
client such as claude.ai registers from its own servers, so every user of a public deployment would otherwise share
one IP's budget — but never from the global quota. Checks run cheapest first: redirect URIs in memory, the per-IP
counter in the RESP store, the quota in Postgres. Either limit is answered HTTP 429 `too_many_requests`.

#### Scenario: Per-IP limit
- **WHEN** one IP exceeds the configured number of registrations within the window
- **THEN** further registrations are answered 429 `too_many_requests`

#### Scenario: Allow-listed redirect URIs bypass the per-IP limit only
- **GIVEN** a configured redirect-URI allow-list
- **WHEN** registrations whose redirect URIs are all allow-listed exceed the per-IP limit
- **THEN** they are still accepted, until the global quota of unused clients is reached

### Requirement: AUTH-13 Client ID Metadata Documents
A `client_id` that is an `https://` URL SHALL identify a client by its metadata document. The authorize endpoint
fetches the document (through the egress policy, [SEC-1](../security/spec.md)), requires its `client_id` to echo the
URL, validates `redirect_uris` against it (the AUTH-2 rule, including a configured allow-list), and caches it for its
`Cache-Control` lifetime (bounded, default 1 h) in the RESP store. Such clients need no registration: the document is
mirrored into the client table when a signed-in user authorizes, so codes, tokens and consent bind to it; the
pre-login check of the request writes nothing. Consent (AUTH-11) shows the document's `client_name`. Advertised via
`client_id_metadata_document_supported: true` in AUTH-1 metadata. Grant types in the document that the gateway does not
implement (claude.ai lists `urn:ietf:params:oauth:grant-type:jwt-bearer`) are ignored, not refused; a document left
without `authorization_code` is refused at authorize per AUTH-4. A document that arrives but fails validation is
reported as invalid, distinct from one that could not be fetched.

#### Scenario: URL client authorizes without registration
- **WHEN** a client whose `client_id` is the https URL of a valid metadata document starts an authorize request
- **THEN** the gateway fetches the document, validates the redirect URI against it, and shows consent naming its
  `client_name`
- **AND** the client is stored only once a signed-in user authorizes

#### Scenario: Document whose client_id does not echo the URL
- **WHEN** the fetched document's `client_id` differs from the URL it was fetched from
- **THEN** the authorize request is refused as an invalid client metadata document, not as an unreachable one

#### Scenario: Unknown grant types are ignored
- **WHEN** the document lists `authorization_code` and the `jwt-bearer` grant
- **THEN** the authorize request proceeds and only `authorization_code` and `refresh_token` are honoured

### Requirement: AUTH-14 Issuer identification (RFC 9207)
Every authorization response, including error redirects, SHALL carry `iss=<issuer>`, and AUTH-1 metadata sets
`authorization_response_iss_parameter_supported: true`.

#### Scenario: Code and error redirects carry iss
- **WHEN** the authorize flow redirects back to the client with a code or with an error
- **THEN** the redirect's query carries `iss` equal to the gateway's issuer
- **AND** the authorization server metadata advertises `authorization_response_iss_parameter_supported: true`

### Requirement: AUTH-15 OIDC login and gateway session
The gateway SHALL be configured through `BUNDLEMCP_OIDC_*` (discovery URL, client id, client secret), perform the
standard OIDC authorization-code flow and establish its own session: an httpOnly cookie carrying a random session id,
with the session record in Valkey for a fixed lifetime of 12 hours. Every login uses PKCE with `S256` (RFC 9700
§2.1.1), as a confidential client too: a fresh verifier is kept with the login's `state` and `nonce`, its challenge goes
on the authorize request and the verifier on the code exchange, so an IdP client that enforces PKCE accepts the login.
Only an IdP whose discovery document lists `code_challenge_methods_supported` without `S256` is sent no PKCE, with a
warning logged at startup. The cookie is host-only, `SameSite=Lax`, and `Secure` exactly when the public URL is https
([DEP-1](../deployment/spec.md), [SEC-4](../security/spec.md)).

#### Scenario: Login carries PKCE
- **WHEN** a browser starts `/login` against an IdP that supports `S256`
- **THEN** the redirect to the IdP carries a `code_challenge` with method `S256`
- **AND** the code exchange on callback sends the matching verifier

#### Scenario: Session cookie follows the public URL
- **WHEN** the login callback succeeds on a deployment whose public URL is https
- **THEN** the session cookie is set httpOnly, `SameSite=Lax` and `Secure`, with a 12-hour max age

#### Scenario: IdP without S256
- **WHEN** the IdP's discovery document lists `code_challenge_methods_supported` without `S256`
- **THEN** logins carry no PKCE parameters and a warning is logged

### Requirement: AUTH-16 Auto-provisioning
First login SHALL auto-provision a `User` from `(issuer, sub)` with email/display name from claims
([architecture](../architecture/spec.md)). The same user store backs OAuth-server logins
([AUTH-3](../auth/spec.md)) — one identity per human, whether they arrive via the admin UI or a connector
authorize flow.

#### Scenario: First login creates the user
- **WHEN** a person logs in for the first time
- **THEN** a user keyed by the IdP's issuer and subject is created with the email and name from the claims

#### Scenario: Later logins reuse the user
- **WHEN** the same person logs in again, through the admin UI or an OAuth authorize flow
- **THEN** the existing user is updated, not duplicated

### Requirement: AUTH-17 Admin role
Users listed in `BUNDLEMCP_ADMIN_EMAILS`, or whose `groups` claim contains `bundlemcp-admin`, SHALL get
`is_admin=true`. The role is **re-evaluated on every login** — demotion in the IdP takes effect at the next login,
promotion likewise; never frozen at first provision. Only admins can access the management UI/API; non-admin users
exist only as endpoint consumers (OAuth tokens, upstream token owners).

#### Scenario: Admin email grants the role
- **WHEN** a user whose email is listed in `BUNDLEMCP_ADMIN_EMAILS` logs in
- **THEN** they are an admin and can call the management API

#### Scenario: Demotion at the next login
- **WHEN** an admin's email is removed from the list and they are no longer in the `bundlemcp-admin` group, and they
  log in again
- **THEN** they are no longer an admin and the management API refuses their session with 401

### Requirement: AUTH-18 No local accounts
There MUST be no local password login, no signup page, and no password-reset flow — by design, not omission.
`docker-compose.yml` ships a lightweight dev IdP ([ARC-13](../architecture/spec.md)) so standalone use needs no
external dependency.

#### Scenario: Standalone stack logs in through the dev IdP
- **WHEN** the compose stack is started without an external IdP
- **THEN** admin login goes through the bundled Keycloak realm and the gateway offers no password form of its own

### Requirement: AUTH-19 Logout
Logout SHALL invalidate the bundlemcp session; single-logout from the IdP is best-effort (front-channel), not required.

#### Scenario: Logout ends the session
- **WHEN** a signed-in admin posts to `/logout`
- **THEN** the session record is deleted and a following management API call with the same cookie answers 401

### Requirement: AUTH-20 Deprovisioning
Admin sessions SHALL have a max age forcing periodic re-login (IdP re-check). An admin (or the management API) can
**deactivate a user**, which immediately ends their browser sessions (every request re-checks that the user is
active) and revokes their issued OAuth tokens ([auth](../auth/spec.md)) and consents. A user deleted or
disabled at the IdP thus loses access at the latest when their session/token lifetimes force renewal — and immediately
when deactivated here.

#### Scenario: Deactivation logs out and revokes
- **WHEN** an admin deactivates a signed-in user
- **THEN** that user's next management API request answers 401
- **AND** their OAuth access and refresh tokens no longer authenticate and their consents are revoked

### Requirement: AUTH-21 IdP availability
The gateway MUST NOT depend on the IdP being reachable when it starts, and readiness never depends on the IdP: an
installer may create the realm only once the gateway is ready. A failed discovery fetch is never kept. A login retries
it, at most once per 5 s, and a background loop retries with exponential backoff capped at 60 s until it succeeds.
Until then `/login` answers `503` with `Retry-After`. Once fetched, the discovery document is refreshed hourly, and a
failed refresh keeps the document already held. The signing keys are fetched on every code exchange. Every fetch
passes the egress policy ([SEC-1](../security/spec.md)). Tokens the gateway issued, API keys and the OAuth metadata
keep working while the IdP is down.

#### Scenario: Login while the IdP is unreachable
- **WHEN** `/login` is requested before the IdP's discovery document could be fetched
- **THEN** the gateway answers 503 with a `Retry-After` header
- **AND** `/readyz` and `/.well-known/oauth-authorization-server` still answer 200

#### Scenario: Failed refresh keeps the document
- **WHEN** the hourly refresh of a previously fetched discovery document fails
- **THEN** logins keep using the document already held

### Requirement: AUTH-22 Key format and one-time display
Keys SHALL have the format `bmcp_sk_<random≥32 bytes urlsafe>`. A key is shown **once** at creation; only `key_hash`
(+ display prefix) is stored ([ARC-18](../architecture/spec.md)).

#### Scenario: Key value is returned only at creation
- **WHEN** an admin creates an API key
- **THEN** the response carries the full `bmcp_sk_…` value once
- **AND** later reads of the key return only its display prefix, and the store holds only the hash

### Requirement: AUTH-23 Name, scope and kind
Keys SHALL carry a `name`, an optional **endpoint scope** (list of endpoint ids; empty = all endpoints), and a
**kind**: `endpoint` (can call scoped endpoints) or `service` (can also call the management API).

#### Scenario: Scoped key outside its scope
- **WHEN** a key scoped to endpoint `a` is presented at endpoint `b`
- **THEN** the request is not authenticated by that key

#### Scenario: Endpoint key at the management API
- **WHEN** an `endpoint`-kind key calls the management API
- **THEN** the gateway answers 403, while a `service`-kind key is accepted

### Requirement: AUTH-24 Accepted headers
Keys SHALL be accepted via `Authorization: Bearer bmcp_sk_…` or the `X-API-Key` header on endpoints with `api_key` in
`auth_modes` ([EP-3](../endpoints/spec.md)). Keys MUST **never** be accepted via a query parameter (decision log).

#### Scenario: Either header authenticates
- **WHEN** a valid key is sent as `Authorization: Bearer` or as `X-API-Key` to an `api_key` endpoint
- **THEN** the request is authenticated as `api_key:<id>`

#### Scenario: Query parameter is ignored
- **WHEN** a valid key is sent only as a URL query parameter
- **THEN** the request is treated as unauthenticated

### Requirement: AUTH-25 Deactivation, deletion and last use
Deactivation (`is_active=false`) and deletion SHALL take effect on the next request on every replica: each request
validates the key against Postgres, and the change also publishes an invalidation event
([SES-19/SES-20](../sessions/spec.md)). `last_used_at` is maintained coarsely (at most one write per key per
minute) for the UI.

#### Scenario: Deactivated key stops working
- **WHEN** an admin deactivates a key
- **THEN** the next request with that key, on any replica, is not authenticated

#### Scenario: Busy key is not written per call
- **WHEN** a key is used several times within a minute
- **THEN** `last_used_at` is updated at most once in that minute

### Requirement: AUTH-26 Validation path
Key validation SHALL hash the presented key and look the digest up in Postgres on every request, without a
validation cache; failed authentications feed the auth rate limiter ([EP-20](../endpoints/spec.md)).

#### Scenario: Unknown key counts as an auth failure
- **WHEN** a request presents a `bmcp_sk_…` value whose digest matches no active key
- **THEN** the request is refused and the failure is counted toward the per-IP auth lockout

### Requirement: AUTH-27 Per-server header mapping
Each server SHALL carry `forward_headers`: a map of client-header → upstream-header names (commonly
`authorization → authorization`). Only explicitly listed headers are forwarded.

#### Scenario: Mapped header is forwarded under its upstream name
- **GIVEN** a server mapping `x-tenant-id → x-tenant`
- **WHEN** a client calls one of its tools with `X-Tenant-Id: tenant-42`
- **THEN** the upstream request carries `x-tenant: tenant-42`

#### Scenario: Unlisted header is not forwarded
- **WHEN** a client sends a header the server does not map
- **THEN** the upstream request does not carry it

### Requirement: AUTH-28 Deny-list
A deny-list SHALL be enforced at write time and at runtime: `host`, `content-length`, `cookie`, `x-api-key`, anything
`sec-*`/`proxy-*`, and the `mcp-session-id` header MUST never be forwardable (metamcp's `DENIED_FORWARD_HEADERS`,
extended).

#### Scenario: Denied header refused at write time
- **WHEN** an admin saves a server whose `forward_headers` names `cookie`, `X-API-Key`, `Sec-Fetch-Mode` or
  `proxy-auth` on either side
- **THEN** the management API refuses the change naming the headers that are never forwarded

#### Scenario: Denied header skipped at runtime
- **WHEN** a stored mapping names a denied header
- **THEN** that header is not forwarded on upstream calls

### Requirement: AUTH-29 Identity header
With the per-server flag `send_identity_header` (default on), the gateway SHALL inject `X-MCP-User: <sub>` (resolved
caller — user id or `api_key:<id>`), and strip any client-supplied `X-MCP-User` unconditionally so it can never be
spoofed. When the caller is anonymous (`none`-auth endpoint) the header is omitted. The deployment-wide setting
`BUNDLEMCP_IDENTITY_SUBJECT` chooses how a user is named: `internal` (default) sends the bundlemcp user id, `oidc`
sends the user's IdP subject (`oidc_sub`, see [architecture](../architecture/spec.md) `User`). API-key callers are
`api_key:<id>` under either value. The default keeps the value existing upstreams key per-user data on.

#### Scenario: Spoofed header is replaced
- **WHEN** an API-key caller sends `X-MCP-User: spoofed` to a server with `send_identity_header` on
- **THEN** the upstream receives `X-MCP-User: api_key:<id>`

#### Scenario: Subject namespace
- **WHEN** `BUNDLEMCP_IDENTITY_SUBJECT=oidc` and a signed-in user calls a tool
- **THEN** `X-MCP-User` carries the user's IdP subject, while an API-key caller is still `api_key:<id>`

#### Scenario: Anonymous caller
- **WHEN** a caller on a `none`-auth endpoint calls a tool
- **THEN** no `X-MCP-User` header is sent

### Requirement: AUTH-30 Introspection for forwarded bearers
Upstreams that need to verify the forwarded bearer SHALL be able to call `POST /oauth/introspect`
([AUTH-5](../auth/spec.md)) — the sequence the first consumer's servers use today against metamcp.

#### Scenario: Upstream verifies a forwarded bearer
- **GIVEN** a server mapping `authorization → authorization`
- **WHEN** the upstream introspects the bearer it received, authenticating with a service key
- **THEN** the gateway reports the token `active` with the caller's `sub`

### Requirement: AUTH-31 Forwarded headers never cross callers
An upstream connection carrying user A's forwarded authorization MUST never serve user B's request
([sessions](../sessions/spec.md)). The gateway SHALL open a fresh upstream connection for every
upstream tool call, built from that request's own forwarded headers, so no upstream connection is reused across
requests or callers.

#### Scenario: Two callers, two connections
- **WHEN** users A and B call the same tool of a server that forwards `authorization`, on the same replica
- **THEN** each upstream request carries only its own caller's forwarded header value

### Requirement: AUTH-32 Delegated tokens (token exchange)
A server with `auth_mode=delegated_token` ([UPS-1](../upstreams/spec.md)) SHALL receive, instead of the
caller's own bearer, a short-lived token the gateway issues for the caller with that **server as its audience**
([ADR-0041](../../../docs/adr/0041-delegated-upstream-tokens.md)) — the RFC 8693 token-exchange model (subject: the
caller's authenticated identity; audience: the upstream), performed inside the gateway. The token is sent as
`Authorization: Bearer`, is minted afresh for every upstream request (only its hash is kept, never the value), is
valid for five minutes, and lives in Valkey only (a restart of any replica does not invalidate it). Introspection
([AUTH-5](../auth/spec.md)) reports it `active` with the caller's `sub` (user id or `api_key:<id>`; a user's
token also carries `oidc_iss` and `oidc_sub`), `aud` = the server's URL, `client_id` = the gateway's own delegation
client, `token_use` = `delegated`, and `act.sub` = the endpoint the caller came through. An anonymous caller gets no
token. Tool discovery has no caller; it sends the server's static headers as for any other server.

#### Scenario: Upstream receives a delegated token
- **WHEN** an authenticated caller calls a tool of a `delegated_token` server
- **THEN** the upstream receives `Authorization: Bearer` with a fresh delegated token, not the caller's own token

#### Scenario: Delegated token introspects with audience and actor
- **WHEN** the upstream introspects the delegated token within five minutes
- **THEN** it is `active` with the caller's `sub`, `aud` the server's URL, `token_use` `delegated` and `act.sub` the
  endpoint
- **AND** after five minutes it is reported inactive

#### Scenario: Anonymous caller gets no token
- **WHEN** an anonymous caller calls a tool of a `delegated_token` server
- **THEN** no delegated token is minted

### Requirement: AUTH-33 Passthrough is labelled, not hidden
A `forward_headers` entry that forwards `authorization` passes the caller's gateway token to the upstream — token
passthrough, which the MCP authorization spec forbids an MCP server to accept. It remains supported for trusted
internal upstreams that introspect it (AUTH-30), but the API SHALL report it as `forwards_caller_token: true` and the UI
shows it as passthrough with `delegated_token` as the conformant alternative.

#### Scenario: Passthrough is flagged
- **WHEN** an admin reads a server whose `forward_headers` forwards `authorization`
- **THEN** the server carries `forwards_caller_token: true`
- **AND** the registration form warns that this is token passthrough and points to the delegated-token option

## Out of scope

### OAuth server

- Acting as a general-purpose IdP (no ID tokens/OIDC provider surface beyond what MCP clients need; human identity
  always comes from the external IdP). This includes `/oauth/userinfo` (metamcp served one) — introspection's `sub`
  covers the known consumers; consciously skipped.
- Scopes/permissions granularity beyond a single default scope in v1 (endpoint binding is via audience, not scopes).

### Admin authentication

- Roles beyond admin/non-admin (single shared workspace — decision log).
- Multi-IdP federation (one configured issuer per deployment).

### API keys

- Per-key rate limits (use the endpoint's per-client limit — the key IS the client identity there).
- Key expiry dates (revocation only, in v1).

### Identity forwarding

- Rewriting/normalizing header values (verbatim forwarding only).
- Signed identity assertions (JWT-style) toward upstreams — `X-MCP-User` is trusted network-internal; if a deployment
  needs proof, upstreams introspect the delegated token (AUTH-32) or, for legacy setups, the forwarded bearer (AUTH-30).
- Exchanging the caller's token at a *third-party* authorization server (RFC 8693 against the upstream's own AS, Entra
  OBO, ID-JAG): no targeted upstream trusts bundlemcp as a subject-token issuer.

## Notes

### OAuth server

Origin: metamcp carry-over, hardened. Prior art: `../metamcp/apps/backend/src/routers/oauth/` (registration,
authorization, token, metadata), `../metamcp/README-oauth.md`.

Resource indicators (RFC 8707) were resolved as required — AUTH-10. Still open: whether claude.ai additionally needs
`client_credentials`; extend AUTH-4 if so.

### Admin authentication

Origin: improvement (metamcp: better-auth local accounts + optional OIDC; bundlemcp: OIDC only). This deletes the
entire class of auth code that caused pain in metamcp.

The bundled dev IdP is Keycloak, for parity with the application layer's production IdP —
[ADR-0015](../../../docs/adr/0015-keycloak-dev-idp.md).

### API keys

Origin: metamcp carry-over (scoping added, query-param mode dropped). Prior art:
`../metamcp/apps/backend/src/middleware/api-key-oauth.middleware.ts`, `api_keys` table.

### Identity forwarding

Origin: metamcp carry-over (fork feature `forward_headers` plus the first consumer's identity contract). Prior art:
`../metamcp/apps/backend/src/lib/metamcp/header-forwarding.ts`, the first consumer's compose stack (seo-gsc/hyperframes
identity contract). This is the contract the first consumer's upstream servers already rely on.

metamcp solved cross-caller connection reuse by bypassing idle-session reuse for servers with forwarded headers;
bundlemcp avoids it by never reusing an upstream connection across tool calls.
