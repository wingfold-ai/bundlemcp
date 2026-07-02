# 21 — Admin authentication (OIDC-only)

**Status:** Accepted · **Origin:** improvement (metamcp: better-auth local accounts + optional OIDC; bundlemcp: OIDC only)

## Summary

Humans authenticate to bundlemcp **exclusively via an external OIDC provider**
(Keycloak in ultra-mcp; any compliant IdP standalone). bundlemcp stores no
passwords and implements no signup — user records are provisioned on first
login. This deletes the entire class of auth code that caused pain in metamcp.

## Requirements

- **ADM-1** Config (`BUNDLEMCP_OIDC_*`): discovery URL, client id, client
  secret. The gateway performs the standard OIDC authorization-code flow and
  establishes its own session (signed httpOnly cookie; session record in
  Redis with configurable lifetime).
- **ADM-2** First login auto-provisions a `User` from `(issuer, sub)` with
  email/display name from claims ([02-domain-model.md](02-domain-model.md)).
  The same user store backs OAuth-server logins ([OAS-3](20-oauth-server.md)) —
  one identity per human, whether they arrive via the admin UI or a
  connector authorize flow.
- **ADM-3** Admin role: users listed in `BUNDLEMCP_ADMIN_EMAILS` (or matching
  a configured claim, e.g. a group/role claim) get `is_admin=true` on
  provision. Only admins can access the management UI/API; non-admin users
  exist only as endpoint consumers (OAuth tokens, upstream token owners).
- **ADM-4** There is no local password login, no signup page, and no
  password-reset flow — by design, not omission. `docker-compose.yml` ships a
  lightweight dev IdP ([ARC-13](01-architecture.md)) so standalone use needs
  no external dependency.
- **ADM-5** Logout invalidates the bundlemcp session; single-logout from the
  IdP is best-effort (front-channel), not required.

## Out of scope

- Roles beyond admin/non-admin (single shared workspace — decision log).
- Multi-IdP federation (one configured issuer per deployment).

## Open questions

- Which dev IdP to bundle in compose (Keycloak vs. dex vs. mock-oidc) —
  smallest image that supports the needed flows wins; decide at implementation.
