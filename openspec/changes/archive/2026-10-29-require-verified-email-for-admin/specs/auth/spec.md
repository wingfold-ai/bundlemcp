## MODIFIED Requirements

### Requirement: AUTH-17 Admin role
Users listed in `BUNDLEMCP_ADMIN_EMAILS`, or whose configured admin claim (`BUNDLEMCP_ADMIN_CLAIM`, a claim name or a
dotted path into nested claims, default `groups`) equals or contains `BUNDLEMCP_ADMIN_CLAIM_VALUE` (default
`bundlemcp-admin`), SHALL get `is_admin=true`. A listed email counts only when the ID token's `email_verified` claim is
`true` (the boolean, or the string `"true"` some providers send); an unverified or absent `email_verified` never grants
the role through the email list, and the login logs a warning naming no address. The role is **re-evaluated on every
login** — demotion in the IdP takes effect at the next login, promotion likewise; never frozen at first provision. Only
admins can access the management UI/API; non-admin users exist only as endpoint consumers (OAuth tokens, upstream token
owners). The management API answers a signed-in user who is not an admin with 403, and a caller with no valid session
or key with 401.

#### Scenario: Admin email grants the role
- **WHEN** a user whose email is listed in `BUNDLEMCP_ADMIN_EMAILS` logs in with `email_verified: true`
- **THEN** they are an admin and can call the management API

#### Scenario: An unverified admin email does not grant the role
- **WHEN** a user whose email is listed in `BUNDLEMCP_ADMIN_EMAILS` logs in with `email_verified: false`, or with no
  `email_verified` claim
- **THEN** they are not an admin, the management API refuses their session with 403, and a warning is logged

#### Scenario: The admin claim needs no verified email
- **GIVEN** the default admin claim settings
- **WHEN** a user without `email_verified` whose ID token carries `groups: ["bundlemcp-admin"]` logs in
- **THEN** they are an admin

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
