# Tasks

## 1. Decide UPS-18

- [x] 1.1 Record the maintainers' choice for UPS-18 (write-free, batch or amend) in this change's proposal and adjust
  the UPS-18 delta and design.md to it; verify with `openspec validate complete-tool-curation --strict`

## 2. Stale tools and write-free sync (UPS-18, UPS-19)

- [x] 2.1 Add `stale_since` to `Tool` and its row class and `last_discovered_at` to `McpServer`, with an Alembic
  revision; verify `alembic upgrade head` and `downgrade -1` run on Postgres
- [x] 2.2 Rewrite `sync_tools` to stage only new, changed, vanished and reappeared tools and count all four as changes;
  verify with domain tests `test_ups18_unchanged_run_stages_nothing` and `test_ups19_vanish_and_reappear_are_changes`
- [x] 2.3 Make `DiscoveryService` set `last_discovered_at` on success and leave tools untouched on failure; verify with
  `test_ups19_failed_probe_makes_nothing_stale` and `test_ups18_unchanged_run_invalidates_nothing`
- [x] 2.4 Add a stale-tool stage to the tool pipeline so `BundleView` excludes stale tools from list and call; verify
  with API tests through the ASGI app `test_ups19_stale_tool_not_listed_and_rejected_on_call` (unknown-tool error,
  denied audit, no metering, no upstream contact) and `test_ups19_reappearing_tool_keeps_curation`
- [x] 2.5 Expose `stale` (and the derived `last_seen_at`) on `ToolRead` and `BundleToolRead`, drop stale tools from
  `catalogue_tools`, and correct the docstrings and field descriptions in `tool_sync.py`, `discovery_service.py`,
  `tool.py` and `tool_read.py`; verify with `test_bnd17_staleness_listed`, `test_bnd17_catalogue_leaves_out_stale_tools`
  and `cd apps/web && npm run openapi`
- [x] 2.6 Add `prune` to `:refresh-tools` (delete stale tools and their curation after a successful probe, report
  `pruned`); verify with `test_ups19_refresh_and_prune_deletes_stale_tools` and
  `test_ups19_prune_after_failed_probe_deletes_nothing`
- [x] 2.7 Document staleness and refresh & prune in `docs/manage/servers.md` and `docs/integrate/management-api.md`;
  verify with `python3 tools/check_docs_links.py` and `tools/check_docs_symbols.py`

## 3. Override names against prefixed names (BND-14)

- [x] 3.1 Add the presented-name policy in `domain/bundles/` and use it in `curate_tool`; verify with
  `test_bnd14_override_equal_to_prefixed_name_conflicts`
- [x] 3.2 Re-check on `add_member` and on `ServerService.rename`; verify with
  `test_bnd14_member_add_collision_conflicts` and `test_bnd14_rename_into_collision_conflicts`
- [x] 3.3 Resolve a discovery-time collision in the view composition (override keeps the name, warning logged); verify
  with `test_bnd14_discovered_collision_keeps_override`
- [x] 3.4 Align `docs/manage/bundles.md` (the uniqueness row and the rename/member-add 409s); verify with
  `uv run rumdl check docs/manage/bundles.md`

## 4. Curation API and UI (BND-16, BND-17)

- [x] 4.1 Add `override_annotations` to `BundleToolRead` and fill it in `BundleService.list_tools`; verify with
  `test_bnd17_annotation_overrides_listed` and `cd apps/web && npm run openapi`
- [x] 4.2 Rework the curation rows in `apps/web/app/pages/bundles/[name].vue`: inline description and annotations (JSON
  validated before save), full-record save, "overridden" also for description and annotations, "stale" badge; verify
  with Playwright scenarios E2E-19 (save keeps API-set overrides) and E2E-20 (stale badge), and `npm run typecheck`
- [x] 4.3 Offer "Refresh & prune" on the upstream detail page with a confirmation listing the stale tools; verify with
  Playwright scenario E2E-20 citing UPS-19 and refresh `apps/web/tests/TESTMAP.md`

## 5. Member order (BND-1, BND-8)

- [x] 5.1 Add `position` to `BundleServer` and its row with an Alembic revision backfilling server-name order; verify
  the migration on a database with two bundles
- [x] 5.2 Append on `add_member`, return memberships by position, and add `PUT /api/v1/bundles/{name}/upstreams:order`;
  verify with `test_bnd1_members_listed_in_member_order`, `test_bnd1_reorder` and
  `test_bnd1_reorder_must_be_permutation`
- [x] 5.3 Keep member order in `BundleView.servers` and the member fan-out; verify with
  `test_bnd8_first_member_in_member_order_wins_uri_collision`
- [x] 5.4 Set positions from a bootstrap document's `upstreams` list; verify with `test_bnd1_bootstrap_sets_order`
- [x] 5.5 Add reorder controls to the members card of the bundle page and document member order in
  `docs/manage/bundles.md`; verify with Playwright scenario E2E-21 citing BND-1 and `npm run openapi`

## 6. Gates

- [x] 6.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .` and `uv run lint-imports`; verify all
  pass with no new exceptions
- [x] 6.2 Run `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py` and
  `check_adr_graph.py`; verify all pass
- [x] 6.3 Run `cd apps/web && npm run openapi && npm run typecheck`; verify `git diff --exit-code apps/web/openapi.json
  apps/web/types/api.d.ts` is clean after commit
- [x] 6.4 Run `openspec validate --all --strict`; verify it passes
