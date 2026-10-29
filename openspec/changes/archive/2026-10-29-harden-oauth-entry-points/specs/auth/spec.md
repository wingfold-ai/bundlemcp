# Spec Delta

## MODIFIED Requirements

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

Registration metadata is bounded, because anyone can register and every accepted value is stored. A registration
MUST be refused with `invalid_client_metadata` when it carries more than 10 redirect URIs, a redirect URI longer than
2048 characters, a `client_name` longer than 200 characters, a `scope` longer than 1000 characters, or more than 10
entries in `grant_types` or in `response_types`. The request body as a whole is bounded per
[SEC-7](../security/spec.md).

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

#### Scenario: Oversized metadata is refused
- **WHEN** a client registers 11 redirect URIs, a 2049-character redirect URI, a 201-character `client_name` or a
  1001-character `scope`
- **THEN** the gateway answers 400 with `error` `invalid_client_metadata` naming the field, and stores no client

#### Scenario: Metadata at the bounds is accepted
- **WHEN** a client registers 10 https redirect URIs, a 200-character `client_name` and a 1000-character `scope`
- **THEN** the gateway answers 201

### Requirement: AUTH-15 OIDC login and gateway session
The gateway SHALL be configured through `BUNDLEMCP_OIDC_*` (discovery URL, client id, client secret), perform the
standard OIDC authorization-code flow and establish its own session: an httpOnly cookie carrying an opaque random
session id, with the session record in Valkey for a configurable lifetime (`BUNDLEMCP_ADMIN_SESSION_LIFETIME`,
seconds, default 12 hours). The cookie's max age equals that lifetime. Every login uses PKCE with `S256` (RFC 9700
§2.1.1), as a confidential client too: a fresh verifier is kept with the login's `state` and `nonce`, its challenge goes
on the authorize request and the verifier on the code exchange, so an IdP client that enforces PKCE accepts the login.
Only an IdP whose discovery document lists `code_challenge_methods_supported` without `S256` is sent no PKCE, with a
warning logged at startup. The cookie is host-only, `SameSite=Lax`, and `Secure` exactly when the public URL is https
([DEP-1](../deployment/spec.md), [SEC-4](../security/spec.md)).

A login MUST be finished only by the browser that started it, so a callback link cannot be handed to someone else
(login CSRF). Starting a login sets a binding cookie holding a fresh random value, and the login's stored state keeps
only that value's hash. The callback establishes no session unless the binding cookie is present and its hash
matches the state's; a callback without it, or with a different one, is answered `400` and signs nobody in. The
binding cookie is host-only, `HttpOnly` and `SameSite=Lax`, lives as long as the login state (10 minutes), and is
cleared by every callback. When the public URL is https it is also `Secure` and carries the `__Host-` name prefix.

#### Scenario: Login carries PKCE
- **WHEN** a browser starts `/login` against an IdP that supports `S256`
- **THEN** the redirect to the IdP carries a `code_challenge` with method `S256`
- **AND** the code exchange on callback sends the matching verifier

#### Scenario: Session cookie follows the public URL
- **WHEN** the login callback succeeds on a deployment whose public URL is https and no lifetime is configured
- **THEN** the session cookie is set httpOnly, host-only, `SameSite=Lax` and `Secure`, with a 12-hour max age

#### Scenario: Configured session lifetime
- **GIVEN** `BUNDLEMCP_ADMIN_SESSION_LIFETIME=3600`
- **WHEN** an admin signs in
- **THEN** the session cookie's max age is 3600 seconds and the session no longer authenticates after an hour

#### Scenario: Out-of-range lifetime is refused at startup
- **WHEN** `BUNDLEMCP_ADMIN_SESSION_LIFETIME` is below 300 seconds or above 30 days
- **THEN** the gateway refuses to start and names the setting

#### Scenario: IdP without S256
- **WHEN** the IdP's discovery document lists `code_challenge_methods_supported` without `S256`
- **THEN** logins carry no PKCE parameters and a warning is logged

#### Scenario: A callback link from another browser signs nobody in
- **GIVEN** an attacker who started a login in their own browser and stopped at the callback URL
- **WHEN** a victim's browser, which never started that login, opens the attacker's callback URL
- **THEN** the gateway answers `400`, sets no session cookie and does not exchange the code

#### Scenario: A binding that does not match is refused
- **GIVEN** a browser that started two logins, so its binding cookie belongs to the second
- **WHEN** the first login's callback arrives
- **THEN** the gateway answers `400` and sets no session cookie

#### Scenario: Binding cookie follows the public URL
- **WHEN** a browser starts `/login` on a deployment whose public URL is https
- **THEN** the binding cookie is named with the `__Host-` prefix and set `Secure`, `HttpOnly`, `SameSite=Lax`,
  `Path=/`, without a `Domain` attribute and with a 600-second max age
- **AND** on a deployment whose public URL is plain http, the cookie has no `__Host-` prefix and no `Secure` attribute

#### Scenario: The callback clears the binding cookie
- **WHEN** a login callback completes, whether it signs the browser in or is refused
- **THEN** the response expires the binding cookie
