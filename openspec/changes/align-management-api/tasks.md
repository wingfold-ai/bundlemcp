# Tasks

## 1. Decide

- [ ] 1.1 Record the maintainers' choice for each of the four open items in the proposal and rewrite or drop the
  matching parts of the MGMT-1, MGMT-4 and MGMT-5 deltas; verify with `openspec validate align-management-api --strict`

## 2. Profiles route and probe action (MGMT-1)

- [ ] 2.1 Add a `ProfileController` serving `GET /api/v1/profiles`, keep `GET /api/v1/endpoints/profiles` as a
  deprecated alias (`deprecated=True` in OpenAPI), and move the UI to the new route; verify with
  `test_api1_profiles_top_level`, `test_api1_profiles_alias_deprecated` and `npm run openapi`
- [ ] 2.2 Add `POST /api/v1/upstreams/{name}:probe` calling a connect-only probe through the discovery service; verify
  with `test_api1_probe_records_connection_state` and `test_api1_probe_leaves_tools_unchanged`
- [ ] 2.3 Document both routes in `docs/integrate/management-api.md`, `docs/manage/endpoints.md` and
  `docs/manage/servers.md`; verify with `python3 tools/check_docs_links.py`

## 3. Registrar upsert (MGMT-4)

- [ ] 3.1 Return the current tool cache from `PUT /api/v1/upstreams/{name}`; verify with
  `test_api4_upsert_response_carries_tool_cache` (no probe scheduled on an unchanged re-apply)
- [ ] 3.2 Replace the generic literal error for `transport` with a message naming the field and `streamable-http`;
  verify with `test_api4_unsupported_transport_pointed_message`
- [ ] 3.3 Update the registrar section of `docs/integrate/management-api.md`; verify with `uv run rumdl check docs`

## 4. Ordering (MGMT-5, only on "build")

- [ ] 4.1 Page a bundle's prompts and resources by creation time then id in the Postgres and in-memory repositories,
      keeping name order for what endpoints serve (BND-25, BND-26); verify with
      `test_api5_bundle_prompts_page_in_creation_order` and the existing BND-26 tests unchanged
- [ ] 4.2 Correct `docs/manage/bundles.md` ("Paginated, in name order"); verify with `python3 tools/check_docs_links.py`

## 5. Endpoint rename UI (EP-8)

- [ ] 5.1 Rework the danger-zone rename in `apps/web/app/pages/endpoints/[name].vue` to show the current and resulting
  URL, the warning, and an acknowledgement that enables the rename and sends `force`; verify with a Playwright spec
  `EP-8 rename states the consequence first` and refresh `apps/web/tests/TESTMAP.md`
- [ ] 5.2 Describe the rename flow in `docs/manage/endpoints.md`; verify with `uv run rumdl check docs/manage`

## 6. Gates

- [ ] 6.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .` and `uv run lint-imports`; verify all
  pass with no new exceptions
- [ ] 6.2 Run `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py` and
  `check_adr_graph.py`; verify all pass
- [ ] 6.3 Run `cd apps/web && npm run openapi && npm run typecheck`; verify the generated files are committed
- [ ] 6.4 Run `openspec validate --all --strict`; verify it passes
