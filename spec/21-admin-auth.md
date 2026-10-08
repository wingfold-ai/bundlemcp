# 21 — Admin authentication (OIDC-only)

**Status:** Accepted · **Origin:** improvement (metamcp: better-auth local accounts + optional OIDC; bundlemcp: OIDC
only)

## Summary

Humans authenticate to bundlemcp **exclusively via an external OIDC provider** (Keycloak in the application layer; any
compliant IdP standalone). bundlemcp stores no passwords and implements no signup — user records are provisioned on
first login. This deletes the entire class of auth code that caused pain in metamcp.

## Requirements

- **ADM-1** Config (`BUNDLEMCP_OIDC_*`): discovery URL, client id, client secret. The gateway performs the standard OIDC
  authorization-code flow and establishes its own session (signed httpOnly cookie; session record in Redis with
  configurable lifetime). Every login uses PKCE with `S256` (RFC 9700 §2.1.1), as a confidential client too: a fresh
  verifier is kept with the login's `state` and `nonce`, its challenge goes on the authorize request and the verifier on
  the code exchange, so an IdP client that enforces PKCE accepts the login. Only an IdP whose discovery document lists
  `code_challenge_methods_supported` without `S256` is sent no PKCE, with a warning logged at startup. Cookie
  `Domain`/`Secure`/`SameSite` derive from the public URL and CSRF policy ([DEP-1](71-deployment.md),
  [SEC-4](70-security.md)).
- **ADM-2** First login auto-provisions a `User` from `(issuer, sub)` with email/display name from claims
  ([02-domain-model.md](02-domain-model.md)). The same user store backs OAuth-server logins
  ([OAS-3](20-oauth-server.md)) — one identity per human, whether they arrive via the admin UI or a connector authorize
  flow.
- **ADM-3** Admin role: users listed in `BUNDLEMCP_ADMIN_EMAILS` (or matching a configured claim, e.g. a group/role
  claim) get `is_admin=true`. The role is **re-evaluated on every login** — demotion in the IdP takes effect at the next
  login, promotion likewise; never frozen at first provision. Only admins can access the management UI/API; non-admin
  users exist only as endpoint consumers (OAuth tokens, upstream token owners).
- **ADM-6 Deprovisioning:** admin sessions have a max age forcing periodic re-login (IdP re-check); an admin (or the
  management API) can **deactivate a user**, which immediately revokes their admin sessions, issued OAuth tokens
  ([20-oauth-server.md](20-oauth-server.md)), consents, and upstream OAuth tokens
  ([23-upstream-oauth.md](23-upstream-oauth.md)). A user deleted or disabled at the IdP thus loses access at the latest
  when their session/ token lifetimes force renewal — and immediately when deactivated here.
- **ADM-4** There is no local password login, no signup page, and no password-reset flow — by design, not omission.
  `docker-compose.yml` ships a lightweight dev IdP ([ARC-13](01-architecture.md)) so standalone use needs no external
  dependency.
- **ADM-5** Logout invalidates the bundlemcp session; single-logout from the IdP is best-effort (front-channel), not
  required.
- **ADM-7** The gateway does not depend on the IdP being reachable when it starts, and readiness never depends on the
  IdP: an installer may create the realm only once the gateway is ready. A failed discovery fetch is never kept. A login
  retries it, at most once per 5 s, and a background loop retries with exponential backoff capped at 60 s until it
  succeeds. Until then `/login` answers `503` with `Retry-After`. Once fetched, the discovery document is refreshed
  hourly, and a failed refresh keeps the document already held. The signing keys are fetched on every code exchange.
  Every fetch passes the egress policy ([SEC-1](70-security.md)). Tokens the gateway issued, API keys and the OAuth
  metadata keep working while the IdP is down.

## Out of scope

- Roles beyond admin/non-admin (single shared workspace — decision log).
- Multi-IdP federation (one configured issuer per deployment).

## Open questions

- ~~Which dev IdP to bundle in compose?~~ **Resolved:** Keycloak, for parity with the application layer's production IdP
  — [ADR-0015](../docs/adr/0015-keycloak-dev-idp.md).
