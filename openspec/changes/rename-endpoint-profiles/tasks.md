# Tasks

## 1. Domain: identifiers and presets

- [ ] 1.1 In `domain/endpoints/endpoint_profile.py` replace `CLAUDE = "claude"` and `CHATGPT = "chatgpt"` with
  `OAUTH_ONLY = "oauth_only"` and `WRITE_AS_READ = "write_as_read"`. Verify that
  `grep -rn "EndpointProfile\.\(CLAUDE\|CHATGPT\)" packages apps` finds nothing.
- [ ] 1.2 Rename `claude_profile.py`/`ClaudeProfile` to `oauth_only_profile.py`/`OauthOnlyProfile`, and
      `chatgpt_profile.py`/`ChatgptProfile` to `write_as_read_profile.py`/`WriteAsReadProfile`. Update
      `profiles/__init__.py` (`__all__`) and `ProfileCatalog.builtin()`. Set the descriptions per design.md, and the
      rule-violation messages to name `oauth_only` / `write_as_read`. Delete `.import_linter_cache`. Verify with
      `uv run lint-imports`.
- [ ] 1.3 Update `tests/domain/test_profile_catalog.py`, `test_tool_pipeline.py` and `test_oauth_entities.py` to the
  new identifiers. Add a test citing EP-23 that `EndpointProfile` has exactly `default`, `oauth_only` and
  `write_as_read`, and that `claude`/`chatgpt` are not members. Verify with
  `uv run pytest -q packages/bundlemcp/tests/domain`.

## 2. Persistence: data migration

- [ ] 2.1 Add Alembic revision `0009` (`infrastructure/postgres/migrations/versions/0009_rename_endpoint_profiles.py`,
  `down_revision = "0008"`). `upgrade()` rewrites `endpoints.profile` from `claude` to `oauth_only` and from `chatgpt`
  to `write_as_read`, and `downgrade()` reverses it. The docstring says the revision is not readable by the previous
  release, so old replicas are stopped before it runs.
- [ ] 2.2 Add a hermetic test in `tests/infrastructure/` citing EP-23. It creates the `endpoints` table on sqlite,
  inserts rows with `claude`, `chatgpt` and `default`, runs revision 0009's `upgrade()` through alembic's
  `MigrationContext`/`Operations`, and asserts the rewritten values. Then it runs `downgrade()` and asserts the
  originals. Verify with `uv run pytest -q packages/bundlemcp/tests/infrastructure`.

## 3. API, bootstrap and seed

- [ ] 3.1 Update the API tests that send or expect the old identifiers (`test_api.py`, `test_gateway.py`,
  `test_oauth.py`, `test_available_endpoints.py`, `test_profile_catalog_api.py`, `test_upstream_connect.py`,
  `test_upstream_connect_tool.py`, `test_idp_subject.py`; where `"claude"` is an OAuth `client_id` and not a profile,
  leave it). Add tests citing EP-23: a `PUT /api/v1/endpoints/{name}` with `profile: chatgpt` answers `422`, and the
  error lists the three accepted values. Also check that the profile listing returns `default`, `oauth_only`,
  `write_as_read`, with a warning only on `write_as_read` (EP-14). Verify with `uv run pytest -q`.
- [ ] 3.2 Add a test in `tests/infrastructure/test_bootstrap.py` citing EP-23: a bootstrap document with
  `profile: claude` fails validation and names the profile field. Verify with `uv run pytest -q`.
- [ ] 3.3 Update `deploy/seed.yaml`: the `claude` endpoint uses `profile: oauth_only` and the `chatgpt` endpoint uses
  `profile: write_as_read`, and fix the comment that names "the claude profile". Check any other bootstrap example
  under `deploy/` and `docs/` the same way. Verify by starting the stack with `TUNNEL=none deploy/stack.sh up`: the
  seed loads, and `GET /api/v1/endpoints/chatgpt` reports `write_as_read`.
- [ ] 3.4 Regenerate the API surface: `cd apps/web && npm run openapi`. Verify that `apps/web/openapi.json` and
  `apps/web/types/api.d.ts` list only the new enum values.

## 4. Web UI

- [ ] 4.1 In `apps/web/app/pages/bundles/[name].vue` and `endpoints/[name].vue`, show the profile warning whenever the
  selected profile's listing entry has a `warning`, instead of comparing against `"chatgpt"`. Verify with
  `npm run typecheck`, and in the running UI: choosing `write_as_read` shows the warning, while `default` and
  `oauth_only` do not.
- [ ] 4.2 In `apps/web/app/pages/catalogue/[bundle].vue`, re-key `CLIENT_LABEL` and the `steps()` switch to
  `oauth_only` (claude.ai steps) and `write_as_read` (ChatGPT steps). Verify that the catalogue page for the seeded
  `demo` bundle shows the claude.ai steps on the `claude` endpoint and the ChatGPT steps on the `chatgpt` endpoint.
- [ ] 4.3 Update the e2e specs and test maps that name the old profiles (`apps/web/tests/bundle-flow.spec.ts`,
  `oauth-consent.spec.ts`, `spec-map.json`, `TESTMAP.md`). Verify that `npx playwright test` passes against the
  local stack.

## 5. Documentation and ADR

- [ ] 5.1 Add `docs/adr/0047-profiles-named-for-what-they-change.md` (MADR, "Amends ADR-0007"): an identifier names
  its effect, the hard rename, and accepting the rolling-update break. Add the "Amended by" link to ADR-0007's status
  line and the entry to `docs/adr/README.md` and `docs/arc42/09-architecture-decisions.md`. Verify with
  `python3 tools/check_adr_graph.py`.
- [ ] 5.2 Rewrite the docs that name the old profiles: `docs/guide/concepts.md` (profiles table: identifier, what it
      changes, recommended for), `guide/glossary.md`, `guide/quickstart.md`, `manage/endpoints.md`, `manage/bundles.md`,
      `connect/claude.md`, `connect/chatgpt.md`, `self-hosting/bootstrap.md`, `self-hosting/troubleshooting.md`,
      `arc42/04-solution-strategy.md` and `arc42/11-risks-and-technical-debt.md`. They keep recommending `oauth_only`
      for claude.ai and `write_as_read` for ChatGPT. Verify that
      `grep -rn "profile.*\`\(claude\|chatgpt\)\`\|\`\(claude\|chatgpt\)\`.*profile" docs --include=*.md
      --exclude-dir=node_modules` finds only ADR-0007 and the upgrade note.
- [ ] 5.3 Add the upgrade note to `docs/self-hosting/deploy.md` (Migrations and upgrades): this release renames the
  profiles, so stop the old replicas before starting the new ones, and edit any bootstrap file to use the new names
  (`claude` → `oauth_only`, `chatgpt` → `write_as_read`). Verify with `python3 tools/check_docs_links.py`.
- [ ] 5.4 Update `examples/echo-mcp/server.py` where a comment or docstring names the chatgpt profile. Verify with
  `uv run ruff check .`.

## 6. Open changes and spec notes

- [ ] 6.1 Replace the old identifiers in the open changes `align-metering-contract` (protocol delta),
  `complete-admin-ui` (admin-ui delta) and `add-inspector` (admin-ui delta and tasks). Verify with
  `openspec validate --all --strict`.
- [ ] 6.2 Edit the *Entities* list in `openspec/specs/architecture/spec.md` (`profile` values) and the *Docs and
  onboarding* note in `openspec/specs/documentation/spec.md` to the new identifiers. Neither is a requirement, so they
  change in place. Verify with `openspec validate --all --strict`.

## 7. Gates

- [ ] 7.1 Run every gate, and confirm each is clean: `uv run pytest -q`, `uv run ruff check .`,
  `uv run rumdl check .`, `uv run lint-imports`, `python3 tools/check_docs_links.py`, `check_docs_symbols.py`,
  `check_docs_settings.py`, `check_adr_graph.py`, `cd apps/web && npm run openapi` (no diff afterwards),
  `python3 tools/check_spec_ids.py`, and `openspec validate --all --strict`.
