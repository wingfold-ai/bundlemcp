# Tasks

## 1. Verified email in the claims (AUTH-17)

- [x] 1.1 Add `email_verified` to `OidcClaims` (domain) and `VerifiedClaims` (application), set it in `JoseOidcProvider`
      from the boolean `True` or the string `"true"`, and verify with
      `test_auth17_email_verified_parsed_from_bool_and_string` in `tests/infrastructure/test_oidc_provider.py` (true,
      `"true"`, false, `"false"`, absent)
- [x] 1.2 Require `email_verified` for the email path in `UserProvisioningService.is_admin`, log
  `user.admin_email_unverified` without the address, and verify with application tests
  `test_auth17_unverified_admin_email_is_not_admin`, `test_auth17_admin_claim_needs_no_verified_email` and the existing
  admin tests updated to send `email_verified: true`
- [x] 1.3 Verify the end-to-end login in `tests/api/test_oidc.py` with `test_auth17_unverified_admin_email_answers_403`,
  and update the `BUNDLEMCP_ADMIN_EMAILS` field description in `Settings` to say the email must be verified

## 2. Documentation

- [x] 2.1 Update `docs/self-hosting/identity-provider.md` (admin role, the Entra app-role example with
      `BUNDLEMCP_ADMIN_CLAIM=roles`), `docs/guide/authentication.md`, `docs/guide/glossary.md` and
      `docs/manage/users.md`, and mark the change breaking in the pull request, from which CI writes the CHANGELOG entry
      (DEP-12); verify with `python3 tools/check_docs_links.py` and `python3 tools/check_docs_settings.py`
- [x] 2.2 Confirm `deploy/keycloak/bundlemcp-realm.json` sets `emailVerified: true` for every seeded user, so the
  compose stack's admin login still works, and verify it by signing in to the compose stack as the seeded admin and
  reaching the management UI

## 3. Gates

- [x] 3.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`, the four
  `tools/check_*.py` scripts (`check_docs_links`, `check_docs_symbols`, `check_docs_settings`, `check_adr_graph`),
  `python3 tools/check_spec_ids.py` and `openspec validate --all --strict`; all pass (no DTO or route changes, so
  `npm run openapi` is not needed)
