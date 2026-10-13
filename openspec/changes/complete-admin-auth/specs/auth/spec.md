## MODIFIED Requirements

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

### Requirement: AUTH-17 Admin role
Users listed in `BUNDLEMCP_ADMIN_EMAILS`, or whose configured admin claim (`BUNDLEMCP_ADMIN_CLAIM`, a claim name or a
dotted path into nested claims, default `groups`) equals or contains `BUNDLEMCP_ADMIN_CLAIM_VALUE` (default
`bundlemcp-admin`), SHALL get `is_admin=true`. The role is **re-evaluated on every login** — demotion in the IdP takes
effect at the next login, promotion likewise; never frozen at first provision. Only admins can access the management
UI/API; non-admin users exist only as endpoint consumers (OAuth tokens, upstream token owners). The management API
answers a signed-in user who is not an admin with 403, and a caller with no valid session or key with 401.

#### Scenario: Admin email grants the role
- **WHEN** a user whose email is listed in `BUNDLEMCP_ADMIN_EMAILS` logs in
- **THEN** they are an admin and can call the management API

#### Scenario: Configured claim grants the role
- **GIVEN** `BUNDLEMCP_ADMIN_CLAIM=realm_access.roles` and `BUNDLEMCP_ADMIN_CLAIM_VALUE=gateway-admin`
- **WHEN** a user whose ID token carries `realm_access.roles` containing `gateway-admin` logs in
- **THEN** they are an admin, while a user carrying only `groups: ["bundlemcp-admin"]` is not

#### Scenario: Demotion at the next login
- **WHEN** an admin's email is removed from the list and their admin claim no longer carries the admin value, and they
  log in again
- **THEN** they are no longer an admin and the management API refuses their session with 403

#### Scenario: No session is still 401
- **WHEN** the management API is called without a session cookie or API key
- **THEN** it answers 401

### Requirement: AUTH-20 Deprovisioning
Admin sessions SHALL have a max age forcing periodic re-login (IdP re-check). An admin (or the management API) can
**deactivate a user**, which immediately ends their browser sessions (every request re-checks that the user is
active) and revokes their issued OAuth tokens ([auth](../auth/spec.md)), consents and
upstream OAuth tokens ([upstreams](../upstreams/spec.md)). A deactivated user stays
deactivated when they sign in at the IdP again: the admin login and the OAuth authorize flow refuse them, until an
admin reactivates the user. Reactivation restores no token, consent or upstream connection. A user deleted or disabled
at the IdP thus loses access at the latest when their session/token lifetimes force renewal — and immediately when
deactivated here.

#### Scenario: Deactivation logs out and revokes
- **WHEN** an admin deactivates a signed-in user
- **THEN** that user's next management API request answers 401
- **AND** their OAuth access and refresh tokens no longer authenticate and their consents are revoked

#### Scenario: Deactivation removes upstream connections
- **GIVEN** a user connected to a `per_user` upstream and the only user so connected
- **WHEN** an admin deactivates that user
- **THEN** the user's upstream OAuth tokens are gone, and the next discovery of that upstream reports "upstream not
  connected" instead of borrowing the deactivated user's token

#### Scenario: Re-login does not reactivate
- **GIVEN** a deactivated user whose IdP account is still active
- **WHEN** they complete the IdP login, through the admin login or an OAuth authorize flow
- **THEN** no session is created and no code is issued, the user sees that their account is deactivated, and the user
  remains deactivated

#### Scenario: Explicit reactivation
- **WHEN** an admin calls `POST /api/v1/users/{user_id}:activate` for a deactivated user
- **THEN** the user can sign in again, and must re-consent and reconnect upstream accounts

### Requirement: AUTH-26 Validation path
Key validation SHALL hash the presented key and look the digest up in Postgres on every request; failed
authentications feed the auth rate limiter ([EP-20](../endpoints/spec.md)). Because the stored
value is a digest of a high-entropy generated key, the lookup needs no constant-time comparison: the timing of a
digest lookup reveals nothing usable about a stored key. A validation cache MAY be added only together with
invalidation events that evict a deactivated or deleted key from every replica within the propagation budget
([SES-19](../sessions/spec.md)); without them, no cache is used.

#### Scenario: Unknown key counts as an auth failure
- **WHEN** a request presents a `bmcp_sk_…` value whose digest matches no active key
- **THEN** the request is refused and the failure is counted toward the per-IP auth lockout

#### Scenario: Deactivated key stops working without delay
- **WHEN** an admin deactivates a key and the same key is presented on the next request, on any replica
- **THEN** the request is refused
