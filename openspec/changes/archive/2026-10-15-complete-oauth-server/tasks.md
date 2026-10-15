# Tasks

## 1. invalid_token challenge (EP-3a)

- [x] 1.1 Tell a presented-but-refused bearer (audience mismatch, expired, revoked, unknown, user inactive) from no
  bearer at all, without exposing which reason applied: the admission gate sees whether a bearer was presented, and
  the authenticators already refuse every invalid one alike; verify with unit tests citing EP-3a
- [x] 1.2 Make the admission gate answer a refused bearer with
  `WWW-Authenticate: Bearer error="invalid_token", resource_metadata="…"` and keep the plain challenge for a request
  without credentials; verify with ASGI tests in `packages/bundlemcp/tests/api/` named for EP-3a covering
  wrong-endpoint, expired, revoked and missing bearers, and that the 401 still counts toward the auth lockout (EP-20)
- [x] 1.3 Update the 401 description in `docs/integrate/http-surface.md` and `docs/guide/authentication.md`, and
  verify `python3 tools/check_docs_links.py` passes

## 2. resource at the token endpoint (AUTH-10)

- [x] 2.1 Accept an optional `resource` form field on `/oauth/token`, carry it on the token request, and have the
  authorization-code and refresh grants compare it with the grant's audience after canonicalising the URL, refusing a
  mismatch with `invalid_target` before any code is consumed or refresh token rotated; verify with tests in
  `packages/bundlemcp/tests/api/test_oauth.py` citing AUTH-10 for matching, mismatched, non-endpoint and absent
  `resource` on both grants
- [x] 2.2 Advertise nothing new in the authorization-server metadata unless a field applies, and update the token
  endpoint section of `docs/guide/authentication.md`; verify the docs link check passes

## 3. Self-service consents (AUTH-11)

- [x] 3.1 Add a service method listing and revoking consents scoped to the calling user (reusing the cascade that
  revokes tokens issued under a consent), and verify with application tests on the memory fakes citing AUTH-11 that
  another user's consent id answers not-found and stays active
- [x] 3.2 Add `GET /api/v1/me/consents` and `DELETE /api/v1/me/consents/{consent_id}` to the `/me` controller, accepting
  only a signed-in user (admin or not) and applying the CSRF origin check to the delete; verify with ASGI tests that a
  user lists and revokes their own consent, a service key and an anonymous caller get 401, and a cross-site delete
  gets 403
- [x] 3.3 Add a "my connections" view to `apps/web` reachable by non-admin users (the catalogue), listing consents with
  a revoke action, using the generated API types; verify with `npm run typecheck` and a Playwright test
- [x] 3.4 Document self-service revocation in `docs/manage/users.md` and verify the docs link check passes

## 4. tools/call in the end-to-end test (AUTH-9)

- [x] 4.1 Extend `tests/integration/test_oauth_flow.py` to call a tool listed on the OAuth endpoint with the access
  token and assert a non-error result, before the refresh step; verify it passes against the compose stack
  (`docker compose -f deploy/docker-compose.yml up`)

## 5. Gates

- [x] 5.1 Run `cd apps/web && npm run openapi` (new `/me/consents` routes and the token form field) and commit the
  regenerated `apps/web/openapi.json` and `apps/web/types/api.d.ts`
- [x] 5.2 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`, and
  `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py`, `check_adr_graph.py`; all
  pass
- [x] 5.3 Run `openspec validate --all --strict` and verify it passes
