# Tasks

## 1. Characterise before restructuring

- [x] 1.1 Record a baseline. Run
  `uv run pytest -q packages/bundlemcp/tests/api/test_gateway.py packages/bundlemcp/tests/api/test_mrtr.py
  packages/bundlemcp/tests/api/test_relay.py packages/bundlemcp/tests/api/test_cancellation.py
  packages/bundlemcp/tests/api/test_metrics_route.py packages/bundlemcp/tests/api/test_modern_edge.py
  packages/bundlemcp/tests/api/test_upstream_session_pooling.py packages/bundlemcp/tests/api/test_member_curation.py
  packages/bundlemcp/tests/api/test_tool_curation.py` and keep the pass count. Together these tests cover the
  buffered, streamed, parked, passthrough, re-run, denied and cancelled tool-call paths, the session `DELETE`, the
  member lists and URI collisions. Verify that every one of them passes on `main`
- [x] 1.2 Add `test_prot3_disconnect_after_passthrough_input_required_is_harmless` to `tests/api/test_mrtr.py`. A
  stateless call whose upstream answers `input_required` emits its result, the client then disconnects, and the
  client's retry is still served. Verify that it passes before any production edit, so it pins the behaviour around
  `_release` that the design's last risk names
- [x] 1.3 Add `test_bnd8_resources_read_logs_a_failing_member_and_reads_the_next` to `tests/api/test_gateway.py`. In the
  session era, the first resource member raises during `resources/read` and the second owns the URI. The read is
  answered by the second member. Verify that it passes before any production edit. It asserts only the result, not the
  log fields, which group 4 changes

## 2. The admitted call is a parameter

- [x] 2.1 Add `api/mcp/tool_call/admitted_call.py`: a frozen `AdmittedCall` with `forwarded`, `credentials`,
  `timeouts` and `handle: CallHandle | None`. Each field carries a description, and the one for `handle` says it is
  `None` when the request has no id. Verify with
  `uv run python -c "from bundlemcp.api.mcp.tool_call.admitted_call import AdmittedCall"`
- [x] 2.2 Change `ToolCall.run()` to take `received = time.monotonic()`, pass it to `_refuse(refusal, received)`, build
  the `AdmittedCall` after the chain admits, and hand it to `render(self, admitted)`. Make `execute`, `_execute`,
  `_upstream_call`, `conclude`, `finish`, `disconnected`, `_pause` and `_release` take it as a parameter. `execute`
  also takes `channel: InputChannel | None`, `conclude` takes `events: CallEvents`, and `_channel` becomes
  `input_channel(admitted, events)`. Delete `attach` and the `_forwarded`, `_credentials`, `_timeouts`, `_handle`,
  `_events` and `_admitted_at` attributes. Verify with
  `grep -n "assert \|_admitted_at\|def attach" packages/bundlemcp/bundlemcp/api/mcp/tool_call/tool_call.py`, which
  must print nothing, and the group 1 test files, which must keep the 1.1 pass count plus the new tests
- [x] 2.3 Update `call_response.py`. `StreamedCallResponse.render(call, admitted)` builds the events, takes
  `call.input_channel(admitted, events)` and passes both on. `BufferedCallResponse.render(call, admitted)` passes
  `channel=None`. Verify with the same test run as 2.2 (the OPS-9 denied-call metric, the PROT-3 disconnect tests, and
  the parked and lost-park MRTR tests in particular)

## 3. Named relay mode and session-era context

- [x] 3.1 Declare `RelayMode = Literal["parked", "passthrough"]` in `relay/request_state.py`, use it for
  `RequestState.mode`, and export it from `relay/__init__.py`. Type `ToolCall._pause(admitted, mode: RelayMode, …)` and
  the bridge's `seal(mode: RelayMode, …)` with it. Verify that
  `grep -rn "type: ignore\[arg-type\]" packages/bundlemcp/bundlemcp/api/mcp` prints nothing, and that
  `test_prot18_a_state_sealed_before_reads_were_bridged_still_unseals` and `test_tampered_or_foreign_state_is_rejected`
  pass unchanged
- [x] 3.2 Add `api/mcp/protocol/session_request_context.py` with `SessionRequestContext(RequestContext)`, whose
  `session: SessionRecord` is required and described. Return it from `SessionMcpAdapter._admit_session` and
  `_session_context`, take it in `UpstreamLeases.end_session`, and delete the asserts at `session_adapter.py:62,85` and
  `upstream_leases.py:162`. Add `test_session_request_context_requires_a_session` to
  `tests/api/test_request_context.py`: constructing one without `session` raises `ValidationError`. Verify that test and
  the session `DELETE` tests in `test_gateway.py` and `test_upstream_session_pooling.py`
- [x] 3.3 Replace the assert at `upstream_leases.py:138` with the combined condition
  `session is not None and lease.binding is not None and lease.binding != request.binding`. Verify with
  `grep -n "assert " packages/bundlemcp/bundlemcp/api/mcp/upstream/upstream_leases.py
  packages/bundlemcp/bundlemcp/api/mcp/routing/adapters/session_adapter.py`, which must print nothing, and the
  `test_upstream_session_pooling.py` binding and resubscribe tests

## 4. Member fan-out

- [x] 4.1 Make `MemberFanout.first()` return the first non-`None` result of `_ask` over its members in member order, and
  delete `each()`. Verify with the 1.3 test, with `test_bnd8_first_member_in_member_order_wins_uri_collision`, and by
  checking that `grep -n "def each" packages/bundlemcp/bundlemcp/api/mcp/dispatch/handlers/member_fanout.py` prints
  nothing
- [x] 4.2 Make `MemberFanout.merged()` gather `_ask` for every member without a shareable snapshot, then fold over the
  members in member order with the existing `seen` and `present` logic. Add three tests to
  `tests/api/test_member_curation.py`:
  - `test_bnd38_live_members_are_asked_concurrently`: two fake members whose `prompts/list` each wait, with a short
    timeout, until the other has been asked; both prompts are listed and each member is contacted once.
  - `test_bnd38_order_holds_when_a_later_member_answers_first`: `zeta` before `alpha`, both listing `file:///a.txt`,
    and `alpha` answers first; the URI is listed once, from `zeta`.
  - `test_bnd38_a_failing_member_does_not_hold_back_the_others`: one member raises; the other's prompts are listed,
    and the failure is logged as `passthrough.member_failed` with a traceback.

  Verify that the three new tests pass, and that the first one fails against the sequential `merged()` (run it once
  before the edit)
- [x] 4.3 Re-run the BND-8 and BND-37 list tests in `test_member_curation.py`, `test_gateway.py`
  (`test_resources_list_passthrough`, `test_passthrough_skips_members_without_the_capability`) and
  `test_tool_curation.py`. Verify that they all pass unchanged

## 5. `BridgedRead` as a model

- [x] 5.1 Make `BridgedRead` a frozen `BaseModel` (no `arbitrary_types_allowed`: every field has a validator, see
  design.md) with a described field for each of `ctx`, `message`, `target`, `arguments`, `members`, `read`, `render`
  and `failed`, and `method` as a property over `message`. Pass keywords at `prompts_get_handler.py:59` and
  `resources_read_handler.py:58`. Verify with `uv run pytest -q packages/bundlemcp/tests/api/test_mrtr.py` (the
  PROT-18 prompt and resource reads, the wrong-method state, and the lost-park re-run)

## 6. Gates

- [x] 6.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`,
  `python3 tools/check_docs_links.py`, `python3 tools/check_docs_symbols.py`, `python3 tools/check_docs_settings.py`,
  `python3 tools/check_adr_graph.py`, `python3 tools/check_compose_ports.py`, `python3 tools/check_spec_ids.py` and
  `openspec validate --all --strict`. Verify that every one passes. No DTO or route changed, so
  `cd apps/web && npm run openapi` is not needed; confirm that with `git diff --stat apps/web` showing nothing
