# Proposal

## Why

The 2026-10-29 code audit found three weaknesses at the gateway's unauthenticated entry points and in how it stores
upstream credentials:

- **Admin login is not bound to the browser that started it (finding S1).** The login `state` lives only in Valkey.
  An attacker can start a login, sign in at the identity provider as themselves, and send a victim their own
  `/login/callback?code=…&state=…` link. The victim's browser is then signed in as the attacker (login CSRF). From
  there the victim may connect their own upstream accounts to the attacker's user. UPS-27 now binds the connect
  callback to the session user, but that does not help here: the session user is the attacker.
- **`/oauth/*` has no request-body limit (finding S2).** The body limit (SEC-7) covers only `/{endpoint}/mcp` and
  `/api/v1`. `POST /oauth/register` reads its JSON body with no cap, before anyone signs in. The registration body
  also puts no bound on the number of `redirect_uris`, nor on the length of a URI, `client_name` or `scope`, and all
  of them are stored.
- **Static upstream credentials are stored in plaintext (finding S3).** Upstream OAuth tokens and client secrets are
  encrypted at rest (ARC-18, DEP-9). Bearer tokens and API keys entered as a server's `static_headers` are not: they
  sit in a plain JSON column, so a database dump or a backup leaks them.

## What Changes

- **Login is bound to the browser** (AUTH-15, modified):
  - `/login` sets a short-lived, `HttpOnly`, `SameSite=Lax` cookie holding a random value. The login state in Valkey
    keeps only its hash.
  - `/login/callback` signs nobody in unless the cookie is present and its hash matches the state. The cookie is
    cleared on every callback.
  - On an https public URL the cookie is named with the `__Host-` prefix and set `Secure`, so neither a sibling
    subdomain nor plain http can plant or read it.
  - The audit suggested a cookie carrying a hash of the state. This change uses a random value instead, because the
    `state` travels through the identity provider's URLs and logs, and a value derived from it would be no secret.
- **Bounded `/oauth/*` bodies** (SEC-7 and AUTH-2, modified):
  - Every path under `/oauth/` refuses a body over a fixed 64 KiB with `413`, before the body is parsed. The `413`
    has the OAuth error shape. Real requests to these routes are under 4 KiB.
  - A registration is refused with `invalid_client_metadata` when it has:
    - more than 10 redirect URIs, or a redirect URI longer than 2048 characters;
    - a `client_name` over 200 characters, or a `scope` over 1000 characters;
    - more than 10 `grant_types` or `response_types`.
- **Static header values are encrypted at rest** (ARC-18, DEP-9 and SEC-10, modified):
  - With `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` set, a server's static header values are stored encrypted, under the same
    keys as upstream tokens.
  - Values stored before the upgrade are encrypted by the background re-encryption pass. The same pass moves them
    to a new key after a rotation.
  - Without keys, the gateway keeps storing them as it does today, so a keyless deployment keeps working. It logs a
    warning at startup naming how many servers hold plaintext header values.
- **No API change.** Header values stay write-only (UPS-3), and export and import (MGMT-18) behave as before.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `auth`: AUTH-15 (the login is bound to the browser that started it) and AUTH-2 (bounds on registration metadata).
- `security`: SEC-7 (a fixed body limit on `/oauth/*`) and SEC-10 (stored static header values are ciphertext).
- `architecture`: ARC-18 (static header values are encrypted at rest, and stay plaintext only when no key is
  configured).
- `deployment`: DEP-9 (rotation and the background pass cover static header values).

No new requirement codes are needed. The reserved codes AUTH-35, AUTH-36, AUTH-37, SEC-12 and SEC-13 stay unused.

## Impact

- **Resolves:** audit findings S1, S2 and S3 (2026-10-29). No GitHub issue.
- **Code:**
  - `api/oauth/controllers/login_controller.py`, `api/oauth/browser_state/oidc_login_state.py`, and a new
    `api/oauth/login_binding_cookie.py`: the login binding.
  - `api/http/request_body_limit.py`: the `/oauth/` limit and its error shape.
  - `application/schemas/oauth/client_registration_request.py`: the field bounds.
  - `infrastructure/postgres/rows/mcp_server_row.py`, `infrastructure/postgres/server_repository.py`,
    `infrastructure/postgres/sqlalchemy_unit_of_work.py` and a new Alembic migration `0017`: encrypted headers.
  - `application/contracts/persistence/server_repository.py` and a moved
    `application/contracts/persistence/stored_secrets.py`.
  - `application/upstream_oauth/secret_reencryption.py` and `reencryption_sweep.py`.
  - `infrastructure/memory/` fakes, and `main/composition_root.py` for the wiring and the startup warning.
- **API:** no DTO shape changes. The `ClientRegistrationRequest` bounds are new constraints on a route that is not in
  the OpenAPI document. Run `npm run openapi` anyway, to confirm nothing drifted.
- **Database:** migration `0017` adds a nullable `mcp_servers.static_headers_encrypted` column. It only adds a column,
  so a replica of the previous release keeps working against the new schema (DEP-5).
- **Behaviour:**
  - A login that started before the upgrade, or in another browser, fails at the callback with `400`, and the user
    starts it again.
  - A registration with oversized metadata, which no known client sends, is now refused.
- **Docs:**
  - A new ADR, ADR-0061 "Static upstream headers are encrypted in the repository". It amends ADR-0017.
  - `docs/self-hosting/configuration.md` (what `BUNDLEMCP_TOKEN_ENCRYPTION_KEYS` and
    `BUNDLEMCP_TOKEN_REENCRYPTION_INTERVAL` cover).
  - `docs/self-hosting/operations.md` (rotation, and the new `sealed` count).
  - `docs/integrate/http-surface.md` and `docs/integrate/errors.md` (the `/oauth/` limit and registration bounds).
  - arc42 §8 (secrets at rest) and §9 (the ADR row).
- **Not covered:**
  - A `Content-Type` check on any surface (design principles §3 names it as a known gap).
  - Refusing static headers outright when no key is configured. See design.md, "Open Questions".
