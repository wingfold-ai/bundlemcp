# Tasks

## 1. Deprovisioning is complete and sticky (AUTH-20, security — lands first)

- [ ] 1.1 Add `delete_for_user(user_id)` to the upstream token repository contract, its Postgres adapter and its
  memory fake, and verify with an infrastructure test on sqlite that only that user's rows (never a shared
  connection's) are deleted
- [ ] 1.2 Call it from `UserService.deactivate` in the same unit of work as the OAuth token and consent revocation,
  and verify with an application test citing AUTH-20 that after deactivation `any_valid_user_connection` no longer
  returns the user's token and discovery of a `per_user` upstream reports "upstream not connected"
- [ ] 1.3 Stop `UserProvisioningService.provision` from setting `is_active = True`, and have the login callback and the
  OAuth authorize flow refuse a deactivated user with a page saying the account is deactivated (SEC-6 headers) and
  no session or code; verify with ASGI tests citing AUTH-20 for both entry points and that the user stays inactive
- [ ] 1.4 Add `UserService.activate` and `POST /api/v1/users/{user_id}:activate` on the user controller, and verify
  with an ASGI test that a reactivated user can sign in and has no consents or upstream tokens restored
- [ ] 1.5 Add a reactivate action for deactivated users in `apps/web/app/pages/users.vue`, verified by
  `npm run typecheck` and a Playwright test
- [ ] 1.6 Correct `docs/manage/users.md` (cascade, sticky deactivation, reactivation) and verify
  `python3 tools/check_docs_links.py` passes

## 2. Configurable admin session lifetime (AUTH-15)

- [ ] 2.1 Add `admin_session_lifetime` to `Settings` (`BUNDLEMCP_ADMIN_SESSION_LIFETIME`, default 43200, `ge=300`,
  `le=2592000`, described for operators) and pass it to the admin session store from the composition root, replacing
  `DEFAULT_MAX_AGE`; verify with tests citing AUTH-15 that the cookie max age and the Valkey TTL follow the setting and
  an out-of-range value fails settings validation
- [ ] 2.2 Document the setting in `docs/self-hosting/configuration.md` and verify `python3 tools/check_docs_settings.py`
  passes

## 3. Configurable admin claim and 403 for non-admins (AUTH-17)

- [ ] 3.1 Add `admin_claim` (default `groups`) and `admin_claim_value` (default `bundlemcp-admin`) to `Settings`; have
  the OIDC adapter hand the provisioning service the raw claims it needs and resolve a dotted path into nested claims,
  accepting a string or a list; verify with application tests citing AUTH-17 for the default, a Keycloak-style
  `realm_access.roles` path, a missing claim and a non-matching value
- [ ] 3.2 Make the management authentication dependency answer 403 for a valid session of a non-admin user and keep
  401 for no session or key; verify with ASGI tests citing AUTH-17 including the demotion scenario
- [ ] 3.3 Check that `apps/web/app/composables/useApi.ts` sends a 403 from a demoted session to the catalogue rather
  than a login loop, and verify with a Playwright test
- [ ] 3.4 Document both settings in `docs/self-hosting/configuration.md` and `docs/self-hosting/identity-provider.md`,
  and verify `python3 tools/check_docs_settings.py` and the docs link check pass

## 4. Key validation path (AUTH-26)

- [ ] 4.1 Only if the open decision is "amend": add a test citing AUTH-26 that a key deactivated through the management
  API is refused on the very next request, and verify no validation cache exists (the requirement text is the
  change). If the decision is "build", replace this group with the key-format change and a constant-time comparison.

## 5. Gates

- [ ] 5.1 Run `cd apps/web && npm run openapi` (new `:activate` route, changed status codes) and verify
  `apps/web/openapi.json` and `apps/web/types/api.d.ts` are regenerated
- [ ] 5.2 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`, and
  `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py`, `check_adr_graph.py`; all
  pass
- [ ] 5.3 Run `openspec validate --all --strict` and verify it passes
