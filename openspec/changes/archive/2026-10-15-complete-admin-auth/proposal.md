# Proposal: complete admin authentication and deprovisioning

## Why

Deactivating a user is meant to cut them off, but today it does not: their upstream OAuth tokens stay stored (and
`per_user` discovery may still borrow them), and their next IdP login silently reactivates the account. Both are
security gaps. Smaller parts of the original admin-auth specification were also never built — a configurable admin
session lifetime, a configurable admin claim, and a 403 (not 401) for a signed-in user who is not an admin.

## What Changes

- **Deactivation is complete and sticky (AUTH-20, security).** Deactivating a user also deletes every upstream OAuth
  token they own, so neither their calls nor `per_user` discovery can use them. A deactivated user stays deactivated
  when they next sign in at the IdP: the admin login and the OAuth authorize flow refuse them. An admin reactivates a
  user explicitly with a new `POST /api/v1/users/{user_id}:activate`; reactivation restores no token, consent or
  upstream connection.
- **Configurable admin session lifetime (AUTH-15).** `BUNDLEMCP_ADMIN_SESSION_LIFETIME` (seconds, default 12 hours)
  sets both the session record's lifetime and the cookie's max age. The cookie description is made precise: an opaque
  random session id, host-only, `HttpOnly`, `SameSite=Lax`, `Secure` exactly when the public URL is https.
- **Configurable admin claim (AUTH-17).** `BUNDLEMCP_ADMIN_CLAIM` (claim name, dotted paths allowed, default `groups`)
  and `BUNDLEMCP_ADMIN_CLAIM_VALUE` (default `bundlemcp-admin`) replace the hard-coded group. A signed-in user who is
  not an admin gets **403** from the management API; 401 stays for a caller with no valid session or key.
  **BREAKING** for API clients that treat any non-2xx from a demoted session as 401.
- **Key validation path (AUTH-26).** The requirement states why a digest lookup is acceptable and when a validation
  cache would be allowed (settled below).

## Decision

Settled by the maintainers on 2026-10-15:

- **AUTH-26: amend.** The gateway keeps looking up the SHA-256 digest of a presented key in Postgres. An attacker
  controls only the input to the hash, not the digest bytes being compared, so the lookup's timing reveals nothing
  usable about a stored key; a constant-time comparison would need a breaking key-format change (a key-id prefix).
  `domain/shared/secrets.py::tokens_equal` stays in use for OAuth client secrets.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `auth`: AUTH-15 (configurable session lifetime, precise cookie wording), AUTH-17 (configurable admin claim, 403
  for a non-admin session), AUTH-20 (upstream tokens revoked on deactivation, deactivation survives re-login, explicit
  reactivation).
- `auth`: AUTH-26 (digest-lookup rationale; validation cache only with invalidation events).

## Impact

- **Code:** `application/management/user_service.py` (cascade and a new `activate`), the upstream token repository
  contract plus its Postgres adapter and memory fake (delete every token of a user),
  `application/oauth_server/user_provisioning_service.py` (no reactivation; configurable claim),
  `api/oauth/controllers/login_controller.py` (refuse a deactivated user),
  `infrastructure/valkey/admin_session_store.py` and `main/composition_root.py` (lifetime from settings),
  `api/http/management_auth.py` (403 for a non-admin session), `application/settings/settings.py` (three new
  settings), `apps/web/app/pages/users.vue` (reactivate action), `apps/web/app/composables/useApi.ts` (403 handling).
- **APIs:** new `POST /api/v1/users/{user_id}:activate`; management API answers 403 instead of 401 to a non-admin
  session (OpenAPI regenerates).
- **Configuration:** `BUNDLEMCP_ADMIN_SESSION_LIFETIME`, `BUNDLEMCP_ADMIN_CLAIM`, `BUNDLEMCP_ADMIN_CLAIM_VALUE`
  (documented in `docs/self-hosting/configuration.md`, checked by `tools/check_docs_settings.py`).
- **Docs:** `docs/manage/users.md` (today it already claims upstream tokens are revoked and that a deactivated user
  "can no longer sign in" — this change makes both true), `docs/self-hosting/identity-provider.md`,
  `docs/self-hosting/configuration.md`.
- **ADR:** none; ADR-0006 (OIDC-only admin auth) covers the model.
- **Dependencies:** none on other open changes. `complete-admin-ui` touches `users.vue` too; whichever lands second
  merges.
