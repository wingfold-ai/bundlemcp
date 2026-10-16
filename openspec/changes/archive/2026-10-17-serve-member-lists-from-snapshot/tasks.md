# Tasks

## 1. Listing snapshots (UPS-24, UPS-38)

- [x] 1.1 Add `ListingKind`, the `MemberListing` entity with `shareable_for` and `sync_member_listing` in
  `domain/servers/`; verify with domain tests `test_ups38_identity_free_listing_shared`,
  `test_ups38_identity_bearing_listing_not_shared` and `test_ups38_server_scope_decides`
- [x] 1.2 Add the `MemberListingRepository` contract, its Postgres adapter, row class, in-memory fake, the `UnitOfWork`
  accessor and Alembic revision 0016; verify with a repository test on sqlite and `alembic upgrade head` /
  `downgrade -1`
- [x] 1.3 Read prompts, resources and resource templates page by page in `FastMcpUpstreamProbe`, keeping scope and
  completeness, and add `ProbedListing` to `ProbeResult`; verify with `test_ups24_listing_stored_as_listed` and
  `test_ups24_long_listing_truncated_and_logged`
- [x] 1.4 Store and compare snapshots in `DiscoveryService.discover`, announcing a changed one; verify with
  `test_ups24_failed_listing_keeps_cache` and `test_ups24_changed_listing_announced`
- [x] 1.5 Add the `listing_snapshot` server setting to the entity, row, DTOs, service, export and bootstrap document,
  the registration form and the upstream detail page; verify with `test_ups38_operator_shares_or_refuses`,
  `test_ups38_setting_round_trips`, a config-transfer round trip, `npm run openapi` and `npx nuxt typecheck`

## 2. Serving (BND-8) and list changes (PROT-10)

- [x] 2.1 Add `MemberListingReader` and serve the three list methods from shareable snapshots in `MemberFanout.merged`,
  falling back to live; verify with `test_bnd8_lists_served_from_snapshot`, `test_bnd8_unshareable_member_listed_live`
  and `test_bnd8_served_lists_stay_live`, and keep the existing BND-8 and BND-37 tests green
- [x] 2.2 Re-discover a member on its prompt or resource list change in `UpstreamNotificationRouter` before
  announcing; verify with `test_prot10_prompt_list_change_refreshes_snapshot` and the existing PROT-10 tests

## 3. Documentation

- [x] 3.1 Write ADR-0059 and update ADR README, `docs/manage/servers.md`, `docs/manage/bundles.md` and arc42 where they
  describe live passthrough; verify with `python3 tools/check_adr_graph.py` and `check_docs_links.py`
- [x] 3.2 Reword the upstreams "Out of scope" note and the bundles BND-8 note on archive; verify with
  `openspec validate --all --strict`

## 4. Gates

- [x] 4.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .` and `uv run lint-imports`; verify all
  pass with no new exceptions
- [x] 4.2 Run `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py`,
  `check_adr_graph.py` and `check_spec_ids.py`; verify all pass
- [x] 4.3 Run `openspec validate --all --strict` and `npx likec4 validate docs/likec4`; verify both pass
- [x] 4.4 Run `cd apps/web && npm run openapi && npx nuxt typecheck && npm run test:map`, and the Playwright suite
  against the rebuilt compose stack; verify all pass
