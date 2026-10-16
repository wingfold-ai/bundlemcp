# Tasks

## 1. Go / no-go

- [x] 1.1 Record the maintainers' go/no-go in the proposal; on no-go, close the change unapplied and stop here; verify
  the decision is linked from the pull request that records it

## 2. Prompt and resource discovery (UPS-24)

- [x] 2.1 Add the `MemberEntry` entity (kind prompt or resource), row classes, repositories, fakes and the Alembic
  revision; verify with `alembic upgrade head` / `downgrade -1` and repository tests on sqlite
- [x] 2.2 Extend the probe to list prompts and resources when advertised, bounded, and sync them hash-gated with
  staleness; verify with `test_ups24_prompts_cached_at_discovery`, `test_ups24_capability_not_advertised_not_asked`,
  `test_ups24_failed_listing_keeps_cache` and `test_ups24_long_listing_truncated_and_logged`
- [x] 2.3 Reword the tool-discovery "Out of scope" note in this change's archive step and document the cache in
  `docs/manage/servers.md`; verify with `uv run rumdl check docs/manage`

## 3. Curation and serving (BND-37, BND-8)

- [x] 3.1 Add the `MemberEntryCuration` entity, rows, repositories and fakes, and load
  their maps into `BundleView`; verify with an application test on the view loader
- [x] 3.2 Apply curation in the `prompts/list`, `prompts/get`, `resources/list` and `resources/read` handlers; verify
  with API tests `test_bnd37_disabled_member_prompt_hidden_and_refused`,
  `test_bnd37_disabled_member_resource_hidden_and_refused`, `test_bnd37_title_override_presented`,
  `test_bnd37_curation_is_per_bundle` and `test_bnd8_served_lists_stay_live`
- [x] 3.3 Add the management routes and DTOs with bundle invalidation; verify with
  `test_bnd37_curation_over_management_api`, `test_bnd7_member_prompt_curation_notifies` and `npm run openapi`
- [x] 3.4 Add the member prompts and resources curation cards to `apps/web/app/pages/bundles/[name].vue`; verify with
  a Playwright spec citing BND-37 and `npm run typecheck`
- [x] 3.5 Write the ADR (next free number) for caching member listings for curation only, and document curation in
  `docs/manage/bundles.md` and `docs/integrate/management-api.md`; verify with `python3 tools/check_adr_graph.py` and
  `check_docs_links.py`

## 4. Gates

- [x] 4.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .` and `uv run lint-imports`; verify all
  pass with no new exceptions
- [x] 4.2 Run `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py` and
  `check_adr_graph.py`; verify all pass
- [x] 4.3 Run `cd apps/web && npm run openapi && npm run typecheck`; verify the generated files are committed
- [x] 4.4 Run `openspec validate --all --strict`; verify it passes
