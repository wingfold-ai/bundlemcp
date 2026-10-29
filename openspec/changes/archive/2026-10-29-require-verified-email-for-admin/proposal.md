# Proposal

## Why

`BUNDLEMCP_ADMIN_EMAILS` grants admin to any login whose ID token carries a listed `email`. Whether the identity
provider verified that address is never checked; `email_verified` is read nowhere. With an IdP that allows self-signup
or unverified email changes (Keycloak with registration enabled, Auth0, many generic OIDC setups), anyone can register
`admin@corp.example` and get full management rights: export with secrets, API keys, every upstream. Users are keyed by
`(issuer, sub)`, so the impostor becomes a second admin account rather than colliding with the real one. The 2026-10-29
code audit found this (finding M2).

## What Changes

- **Admin by email needs a verified email** (AUTH-17, modified): a listed email grants admin only when the ID token's
  `email_verified` claim is true. The admin claim (`BUNDLEMCP_ADMIN_CLAIM`/`_VALUE`) is unaffected.
- **BREAKING** for deployments whose IdP omits `email_verified` (Microsoft Entra ID, for one) and that rely on
  `BUNDLEMCP_ADMIN_EMAILS`. Such admins lose the role at their next login and must be granted it through the admin
  claim (for example an app role). The release notes and the identity-provider guide say so.
- A login whose email is listed but unverified is logged as a warning, so an operator can see why a listed admin did
  not get the role.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `auth`: AUTH-17 (an admin email counts only when the IdP marks it verified).

## Impact

- **Resolves:** audit finding M2 (2026-10-29). No GitHub issue.
- **Code:**
  - `domain/access/oidc_claims.py`: `OidcClaims` gains `email_verified`.
  - `infrastructure/oidc/jose_oidc_provider.py` fills it.
  - `application/oauth_server/user_provisioning_service.py`: `VerifiedClaims` and `is_admin`.
- **Behaviour:** the role is re-evaluated at every login (AUTH-17), so the change takes effect at each admin's next
  login. Sessions that already exist keep the `is_admin` value stored at their last login until then.
- **Settings:** none added. The `BUNDLEMCP_ADMIN_EMAILS` description says the email must be verified.
- **Docs:** `docs/self-hosting/identity-provider.md` (admin role; Entra/Okta notes), `docs/guide/authentication.md`,
  `docs/guide/glossary.md`, `docs/manage/users.md`. The pull request is marked breaking, and CI writes the CHANGELOG
  entry from it (DEP-12). The dev Keycloak realm
  already sets `emailVerified: true` for its users, so the compose stack keeps working.
- **Not covered:** treating the stored `email` as verified anywhere else. It is still shown as reported. No ADR: this
  tightens an existing rule.
