# Tasks

## 1. Decide

- [x] 1.1 Record the maintainers' choice for each of the four open items in the proposal and rewrite or drop the
  matching parts of the MGMT-1, MGMT-4 and MGMT-5 deltas; verify with `openspec validate align-management-api --strict`

## 2. Registrar upsert (MGMT-4)

- [x] 2.1 Replace the generic literal error for `transport` with a message naming the field and `streamable-http`;
  verify with `test_api4_unsupported_transport_pointed_message`
- [x] 2.2 Update the registrar section of `docs/integrate/management-api.md`; verify with `uv run rumdl check docs`

## 3. Endpoint rename UI (EP-8)

- [x] 3.1 Rework the danger-zone rename in `apps/web/app/pages/endpoints/[name].vue` to show the current and resulting
  URL, the warning, and an acknowledgement that enables the rename and sends `force`; verify with a Playwright spec
  `EP-8 rename states the consequence first` and refresh `apps/web/tests/TESTMAP.md`
- [x] 3.2 Describe the rename flow in `docs/manage/endpoints.md`; verify with `uv run rumdl check docs/manage`

## 4. Gates

- [x] 4.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .` and `uv run lint-imports`; verify all
  pass with no new exceptions
- [x] 4.2 Run `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py` and
  `check_adr_graph.py`; verify all pass
- [x] 4.3 Run `cd apps/web && npm run openapi && npm run typecheck`; verify the generated files are committed
- [x] 4.4 Run `openspec validate --all --strict`; verify it passes
