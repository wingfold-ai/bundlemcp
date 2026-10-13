# Tasks

## 1. Operator-facing docs

- [x] 1.1 In `docs/self-hosting/deploy.md`, replace "Redirects are not followed, so there is no per-hop gap" with an
  accurate statement (the MCP client follows redirects and the egress check is not repeated per hop) and verify
  against `infrastructure/egress/` and the FastMCP transport that the sentence matches the code
- [x] 1.2 In the same file, state that the admin session cookie is host-only (no `Domain`) and that only `Secure`
  follows the public URL's scheme; verify against `api/oauth/controllers/login_controller.py`
- [x] 1.3 Fix `README.md` quickstart step 2 (default seed: `echo` and `oauth-demo`; fleet in `deploy/seed.fleet.yaml`)
  and verify against `deploy/seed.yaml`
- [x] 1.4 Fix `docs/manage/audit.md` (UI filters are time range, endpoint, tool, status; rejections go to logs; list is
  newest first) and verify against `apps/web/app/pages/audit.vue` and `AuditService`
- [x] 1.5 Fix the docs that state an unread setting as working: `docs/manage/servers.md`,
  `docs/self-hosting/configuration.md` and `docs/self-hosting/operations.md` say `server_error_attempts` sets the
  health threshold, but nothing reads it (the threshold is a fixed 3; see complete-upstream-health); verify against
  `application/discovery/discovery_service.py`
- [x] 1.6 Fix `docs/manage/bundles.md`: it claims override names are checked against prefixed `server__tool` names (only
  other override names are checked; see complete-tool-curation) and that a self-reference is rejected at membership
  creation (it is not; see add-self-reference-guard); verify against `application/management/bundle_service.py`
- [x] 1.7 Fix `docs/manage/endpoints.md`: an audience mismatch answers with the generic challenge, not
  `error="invalid_token"` (see complete-oauth-server); verify against
  `api/mcp/routing/authentication/auth_challenge.py`
- [x] 1.8 Fix `docs/manage/users.md`: deactivation revokes the user's gateway tokens and consents but not their upstream
  OAuth tokens, and the next sign-in at the identity provider reactivates the user (see complete-admin-auth); verify
  against `application/management/user_service.py` and `user_provisioning_service.py`

## 2. Architecture docs

- [x] 2.1 In `docs/arc42/10-quality-requirements.md`, drop the claim that an audience mismatch answers
  `error="invalid_token"`; verify against `auth_challenge.py`
- [x] 2.2 In `docs/arc42/11-risks-and-technical-debt.md`, remove "Inspector covers tools only" and correct the
  upstream `list_changed` / push sentence to "not delivered" (between or within calls); verify against
  `api/mcp/` that no upstream notification is forwarded
- [x] 2.3 Rewrite `packages/bundlemcp/bundlemcp/api/mcp/README.md`: replace every deleted module name with the current
  module, drop `_drive_upstream`, and state that the session TTL is a fixed 24 h with `session_lifetime` registered but
  unused; verify `python3 tools/check_docs_symbols.py` and that `grep -E "composition\.py|streams\.py|signals\.py|
  metering\.py|upstream\.py|_drive_upstream"` finds nothing in it

## 3. Docstrings and field descriptions

- [x] 3.1 Correct the module and function docstrings of `infrastructure/config/structured_logging.py` to stderr and
  verify by reading `logging.StreamHandler()`'s default stream
- [x] 3.2 Remove the `/metrics` export claim from `infrastructure/inprocess/counters.py` and the "exported as a metric
  (OPS-9)" comment from `infrastructure/postgres/audit_writer.py`; verify `uv run ruff check .`
- [x] 3.3 Correct the docstrings and field descriptions that say a vanished tool stops being served (it is still
  served; see complete-tool-curation): `domain/servers/tool_sync.py`, `application/discovery/discovery_service.py`,
  `domain/servers/tool.py`, `application/schemas/tools/tool_read.py` and `infrastructure/postgres/rows/tool_row.py`;
  `ToolRead` is a DTO, so run `cd apps/web && npm run openapi` and commit the regenerated files
- [x] 3.4 Correct `UpstreamBinding.identity_key`'s description to what is stored (the caller's `sub`, not yet read) and
  verify `uv run pytest -q packages/bundlemcp/tests/domain` passes (the model is not a DTO, so OpenAPI is unaffected)

## 4. Gates

- [x] 4.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports` and verify all
  pass
- [x] 4.2 Run `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py`,
  `check_adr_graph.py` and verify all pass
- [x] 4.3 Run `openspec validate --all --strict` and verify it passes
