# Tasks

## 1. invalid_token challenge (EP-3a)

- [ ] 1.1 Let the OAuth bearer authenticator report that a bearer was presented but refused (audience mismatch,
  expired, revoked, unknown, user inactive) as distinct from no bearer at all, without exposing which reason applied,
  and verify with unit tests in `packages/bundlemcp/tests/application/` citing EP-3a
- [ ] 1.2 Make the admission gate answer a refused bearer with
  `WWW-Authenticate: Bearer error="invalid_token", resource_metadata="…"` and keep the plain challenge for a request
  without credentials; verify with ASGI tests in `packages/bundlemcp/tests/api/` named for EP-3a covering
  wrong-endpoint, expired, revoked and missing bearers, and that the 401 still counts toward the auth lockout (EP-20)
- [ ] 1.3 Update the 401 description in `docs/integrate/http-surface.md` and `docs/guide/authentication.md`, and
  verify `python3 tools/check_docs_links.py` passes

## 2. Introspection by client credentials (AUTH-5) — only if the open decision is "build"

- [ ] 2.1 Add a per-client "may introspect" flag to the OAuth client entity and its row class with an Alembic
  migration, defaulting to false for every existing and dynamically registered client, and verify the migration
  round-trips in the sqlite infrastructure tests
- [ ] 2.2 Add a management route for an admin to grant and withdraw the flag (DTO in `application/schemas/`, every
  field described), and verify with an ASGI test that a non-admin caller is refused
- [ ] 2.3 Extend the introspection authentication dependency to accept HTTP Basic client credentials of a flagged
  confidential client, checked with the client-secret comparison the token endpoint uses, and count failures toward
  the auth lockout; verify with tests citing AUTH-5 that an authorised client succeeds and a merely registered client
  gets 401
- [ ] 2.4 Document the option in `docs/integrate/upstream-identity.md` and `docs/manage/` and verify the docs link check
  passes

## 3. resource at the token endpoint (AUTH-10)

- [ ] 3.1 Accept an optional `resource` form field on `/oauth/token`, carry it on the token request, and have the
  authorization-code and refresh grants compare it with the grant's audience after canonicalising the URL, refusing a
  mismatch with `invalid_target` before any code is consumed or refresh token rotated; verify with tests in
  `packages/bundlemcp/tests/api/test_oauth.py` citing AUTH-10 for matching, mismatched, non-endpoint and absent
  `resource` on both grants
- [ ] 3.2 Advertise nothing new in the authorization-server metadata unless a field applies, and update the token
  endpoint section of `docs/guide/authentication.md`; verify the docs link check passes

## 4. Self-service consents (AUTH-11)

- [ ] 4.1 Add a service method listing and revoking consents scoped to the calling user (reusing the cascade that
  revokes tokens issued under a consent), and verify with application tests on the memory fakes citing AUTH-11 that
  another user's consent id answers not-found and stays active
- [ ] 4.2 Add `GET /api/v1/me/consents` and `DELETE /api/v1/me/consents/{consent_id}` to the `/me` controller, accepting
  only a signed-in user (admin or not) and applying the CSRF origin check to the delete; verify with ASGI tests that a
  user lists and revokes their own consent, a service key and an anonymous caller get 401, and a cross-site delete
  gets 403
- [ ] 4.3 Add a "my connections" view to `apps/web` reachable by non-admin users (the catalogue), listing consents with
  a revoke action, using the generated API types; verify with `npm run typecheck` and a Playwright test
- [ ] 4.4 Document self-service revocation in `docs/manage/users.md` and verify the docs link check passes

## 5. tools/call in the end-to-end test (AUTH-9)

- [ ] 5.1 Extend `tests/integration/test_oauth_flow.py` to call a tool listed on the OAuth endpoint with the access
  token and assert a non-error result, before the refresh step; verify it passes against the compose stack
  (`docker compose -f deploy/docker-compose.yml up`)

## 6. Gates

- [ ] 6.1 Run `cd apps/web && npm run openapi` (new `/me/consents` routes and the token form field) and commit the
  regenerated `apps/web/openapi.json` and `apps/web/types/api.d.ts`
- [ ] 6.2 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`, and
  `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py`, `check_adr_graph.py`; all
  pass
- [ ] 6.3 Run `openspec validate --all --strict` and verify it passes
