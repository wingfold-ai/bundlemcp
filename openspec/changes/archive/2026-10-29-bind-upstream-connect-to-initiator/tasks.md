# Tasks

## 1. Callback bound to the initiator (UPS-27)

- [x] 1.1 Add `UpstreamConnectState.refusal_for(user)` returning a `ConnectRefusal` or None (per-user: same user;
  shared: an admin; no user: never),
  and verify it with unit tests `test_ups27_state_completed_only_by_initiator` and
  `test_ups27_shared_state_completed_only_by_admin`
- [x] 1.2 Make `UpstreamConnectController.callback` take `CurrentSessionUserProvider` and refuse before the `iss` check
  and `complete_authorize`, with a 403 `connect_refused.html` page and an `upstream_oauth.connect_refused` warning that
  carries no user ids. Verify with api tests in `tests/api/test_upstream_connect.py`:
  `test_ups27_another_user_cannot_finish_per_user_connect` (asserts no token row and that the fake upstream token
  endpoint was not called), `test_ups27_callback_without_session_is_refused`,
  `test_ups27_non_admin_cannot_finish_shared_connect`, and the existing `test_connect_flow_stores_encrypted_token` and
  `test_callback_validates_the_issuer` still passing with a session cookie
- [x] 1.3 Document in `docs/manage/servers.md` (connect flow) that the connect must be finished in the browser and
  account that started it, and verify with `python3 tools/check_docs_links.py`

## 2. Gates

- [x] 2.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`,
  `python3 tools/check_docs_links.py`, `python3 tools/check_docs_symbols.py`, `python3 tools/check_docs_settings.py`,
  `python3 tools/check_adr_graph.py`, `python3 tools/check_spec_ids.py` and `openspec validate --all --strict`; all pass
  (no DTO or route in the OpenAPI document changes, so `npm run openapi` is not needed)
