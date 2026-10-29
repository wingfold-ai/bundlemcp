# Tasks

## 1. Typed member notifications (PROT-7, PROT-23)

- [x] 1.1 Add `LogLevel` (a `Literal` of the eight MCP levels) to `domain/sessions/log_levels.py` and derive
  `LOG_LEVELS` from it with `get_args`. Verify with a domain test that `LOG_LEVELS` keeps its order and `at_least`
  behaves as before, and that the existing setLevel and stateless-adapter tests pass unchanged
- [x] 1.2 Add `application/contracts/upstream/member_notification.py`: `ListedKind`, the frozen `MemberListChanged`,
      `MemberResourceUpdated` and `MemberLogMessage` models (every field described), the discriminated
      `MemberNotification` union, and each model's `notification()` building the relayed JSON-RPC notification from its
      own fields only (implementation note: the update and the log message only; a list change is never relayed as
      heard, so `MemberListChanged` has no caller for one — see design.md). Verify with application tests
      `test_prot7_relayed_log_carries_level_logger_and_data_only` and `test_prot23_relayed_update_carries_the_uri_only`,
      plus a test that an empty URI and a level outside the eight fail validation
- [x] 1.3 Change `UpstreamNotificationSink.received` to take a `MemberNotification`, and verify with
  `uv run lint-imports` that the contract still names no driver

## 2. Handler registry in the application layer (PROT-7, PROT-10, PROT-23)

- [x] 2.1 Add `application/serving/member_notifications/` with the `MemberNotificationHandler` protocol,
  `MemberListChangeHandler`, `MemberResourceUpdateHandler`, `MemberLogMessageHandler` and `MemberNotificationRouter`
  (a `{type: handler}` registry that logs and ignores an unregistered type), moving the behaviour of
  `upstream_notification_router.py` without change, then delete that module. Verify with application tests on the
  `infrastructure/memory` fakes: `test_prot10_one_list_change_is_claimed_once`,
  `test_prot10_failed_rediscovery_still_announces_a_prompt_list_change`,
  `test_prot23_update_reaches_every_subscribed_stream`, `test_prot7_log_below_the_session_level_is_not_delivered`,
  `test_prot7_log_on_a_shared_session_is_not_delivered`, and a router test that an unregistered type is ignored
- [x] 2.2 Wire the three handlers and the router in `main/composition_root.py`, and verify with the existing
  `tests/api/test_member_notifications.py` PROT-7, PROT-10, PROT-17 and PROT-23 tests passing unchanged
- [x] 2.3 Update arc42 §6.5 (`docs/arc42/06-runtime-view.md`) to name the router's registry and the typed notification,
  and verify with `python3 tools/check_docs_symbols.py` and `python3 tools/check_docs_links.py`

## 3. Translation at the pool boundary (PROT-7, PROT-23)

- [x] 3.1 Add `infrastructure/fastmcp/member_notification_translation.py` (`from_server_notification`,
  `from_listen_event`, each a table keyed by SDK type), and make `message_handler`, `log_handler` and `_listen` in
  `pooled_upstream_sessions.py` pass typed notifications to `_notify`; remove `SERVER_NOTIFICATIONS`, `_LISTEN_EVENTS`,
  `_listened` and the dict building. Verify with infrastructure tests that each SDK notification and listen event
  maps to its model, an unknown SDK type maps to `None`, and a log message that does not validate is dropped
- [x] 3.2 Verify end to end in `tests/api/test_member_notifications.py` with
  `test_prot7_a_members_meta_is_not_relayed_with_its_log` and
  `test_prot23_a_members_meta_is_not_relayed_with_an_update` (the test upstream announces each with a `_meta` of its
  own; the GET stream receives none of it)

## 4. Resource watch per upstream era (PROT-23)

- [x] 4.1 Add `infrastructure/fastmcp/resource_watch.py` with `SubscribeResourceWatch` (sends `SubscribeRequest` /
      `UnsubscribeRequest` through `client.session.send_request`) and `ListenResourceWatch` (changes the watched set and
      re-opens the listen stream), chosen when the session connects; `PooledLease.subscribe` / `unsubscribe` delegate to
      it, keeping the drop-before-unsubscribe order. Verify that
      `uv run pytest -q packages/bundlemcp/tests/api/test_member_notifications.py` warns no `resources/subscribe` or
      `resources/unsubscribe` deprecation, and that the existing PROT-23 and PROT-17 tests still record
      `resources/subscribe` and `resources/unsubscribe` upstream. (Implementation note: the planned
      `-W error::mcp.shared.exceptions.MCPDeprecationWarning` run still fails the two PROT-7 tests that send
      `logging/setLevel`, whose SDK helper is deprecated the same way and is a non-goal of this change; the run turns
      no `resources/subscribe` or `resources/unsubscribe` warning into an error.)
- [x] 4.2 Add a modern-era member (pinned to the 2026-07-28 revision) to the member-notification test fixtures and
  verify with `test_prot23_a_modern_member_is_watched_through_its_listen_stream`: no `resources/subscribe` reaches the
  member, its listen filter names the URI, and an update reaches the client's GET stream

## 5. Refetch after a re-opened listen stream (PROT-30)

- [x] 5.1 In `_listen`, remember whether the task has had an acknowledged stream; after each later acknowledged
  re-open, pass a `MemberListChanged` per list in the filter and a `MemberResourceUpdated` per watched URI through
  `_notify`. Verify with `test_prot30_a_list_change_made_while_the_stream_was_down` (drop the modern member's listen
  stream, add a tool, the client's GET stream receives `notifications/tools/list_changed` and discovery runs once),
  `test_prot30_a_watched_resource_after_a_reopen`, `test_prot30_the_first_open_refetches_nothing` and
  `test_prot30_a_filter_change_is_not_a_loss`
- [x] 5.2 Write ADR-0062 "Member notifications are typed at the pool boundary" (extends ADR-0027 and ADR-0054: the
  typed union and registry, explicit handshake-era subscribe requests, refetch after a re-opened listen stream), list
  it in `docs/adr/README.md`, and verify with `python3 tools/check_adr_graph.py` and `python3 tools/check_docs_links.py`

## 6. Gates

- [x] 6.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports` (delete
  `.import_linter_cache` first, since a module moves), `python3 tools/check_docs_links.py`,
  `python3 tools/check_docs_symbols.py`, `python3 tools/check_docs_settings.py`, `python3 tools/check_adr_graph.py`,
  `python3 tools/check_compose_ports.py`, `python3 tools/check_spec_ids.py` and `openspec validate --all --strict`; all
  pass. No DTO or route changes, so `npm run openapi` is not needed
