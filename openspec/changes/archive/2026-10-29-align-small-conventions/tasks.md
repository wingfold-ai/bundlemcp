# Tasks

## 1. One audit filter rule

- [x] 1.1 Add `AuditFilter.matches(record: AuditRecord) -> bool` in `application/management/audit_filter.py`. Make
  `InMemoryAuditRepository` filter with it, delete `_matches`, and sort `page()` by `(created_at, id)` descending.
  Verify with `uv run lint-imports` and the existing `tests/api/test_audit_api.py`
- [x] 1.2 Rewrite `SqlAlchemyAuditRepository._criteria` as a field-to-column table for the equality filters, with the
  two range filters and the tool rule (upstream or client-visible name) written once beside it. Order `page()` by
  `created_at desc, id desc`. Verify with the existing audit API, export and retention tests
- [x] 1.3 Add `tests/infrastructure/test_audit_repository_contract.py`, parametrised over the in-memory and the sqlite
  unit of work. Seed the same records in both, two of them sharing a `created_at`. Verify with
  `test_ops6_filters_agree_across_repositories` (one case per filter field, plus the tool filter matching either
  name) and `test_ops6_newest_first_with_ties_broken_by_id`, run on `page()` and `page_after()`: both repositories
  return identical ids in identical order

## 2. The injected clock

- [x] 2.1 Give `DiscoveryService` a required keyword `clock: Clock` and use it for the discovery timestamp at
  `discovery_service.py:174`. Wire the composition root's `clock`, and update the test constructors in
  `tests/infrastructure/test_discovery.py`, `tests/application/test_upstream_health_on_fakes.py` and any other test
  that builds one. Verify with `test_ups19_stale_since_is_the_injected_instant`, which uses a `ManualClock` and
  checks that a vanished tool's `stale_since` and the server's `last_discovered_at` equal the clock's instant
- [x] 2.2 Give `UserService` a required keyword `clock: Clock` for consent revocation (`user_service.py:36,76`), pass
  `container.clock` in `get_user_service` (`api/http/service_providers.py:114`), and update the test constructors.
  Verify with `test_auth25_deactivation_revokes_consents_at_the_clock_instant` and
  `test_auth11_revoked_consent_carries_the_clock_instant` on fakes with a `ManualClock`
- [x] 2.3 Give `ValkeySessionStore` a required keyword `clock: Clock` and stamp `last_active_at` in `touch` from it.
  Leave the `SessionStore` contract unchanged and wire the composition root. Verify with
  `test_ses10_touch_and_sweep_read_one_clock`: with a `ManualClock`, a touched session is not idle until the clock
  passes the lifetime, and is idle one second after
- [x] 2.4 Give `ValkeyPausedInvocations` a required keyword `clock: Clock` and compute the TTL from
  `self._clock.now().timestamp()`. Wire the composition root. Verify with `test_ses16_pause_ttl_follows_the_clock` in
  `tests/infrastructure/test_paused_invocations.py`: the stored TTL is the expiry minus the clock's time, plus the
  sweep grace
- [x] 2.5 Confirm that `grep -rn "utcnow()\|time\.time()" packages/bundlemcp/bundlemcp` lists only
  `domain/shared/clock.py`, `system_clock.py`, `default_factory` timestamps, and the three tool-call and relay sites
  this change leaves to `make-tool-call-order-explicit` (`tool_call.py`, `input_required_bridge.py`,
  `request_state.py`)

## 3. Safe, useful tracebacks

- [x] 3.1 Add `TracebackRenderer` in `infrastructure/config/traceback_renderer.py`. It replaces `exc_info` with an
  `exception` string that walks the cause and context chain as the standard library does, formats each link's frames
  with `traceback.StackSummary.extract(..., capture_locals=False)`, and renders each Pydantic `ValidationError` in the
  chain from `errors(include_input=False, include_url=False)` (see design, Exception rendering, for why not
  `TracebackException`). Add it to
  `_shared_processors()`, and build `ConsoleRenderer` with `exception_formatter=structlog.dev.plain_traceback`. Verify
  with `test_ops8_logged_exception_carries_its_traceback` (json: one object whose `exception` names the type, the
  message and a frame) and `test_ops8_traceback_never_shows_locals` (json and text, a local holding a token, checked
  with `tests/redaction.py`'s `assert_redacted`) in `tests/infrastructure/test_structured_logging.py`
- [x] 3.2 Verify with `test_sec10_validation_error_input_is_not_logged` that a `ValidationError` raised over a
  secret-bearing value is logged without the value. Verify with `test_ops8_live_log_entry_carries_the_same_traceback`
  that the live log handler's entry carries the same `exception` field as the process log line (in
  `tests/infrastructure/test_live_log.py`)
- [x] 3.3 Set `hide_parameters=True` in `postgres/engine.py` `create_engine`, and on the Alembic engine in
  `postgres/migrations/env.py`, whose data migrations bind ciphertexts too. Verify with
  `test_sec10_database_errors_hide_statement_parameters`: an integrity error on a row carrying a ciphertext, logged
  with `exc_info`, does not contain the ciphertext
- [x] 3.4 Pass `exc_info=True` at `fastmcp/upstream_probe.py:141`, `dispatch/handlers/completion_handler.py:55`,
  `upstream_oauth/upstream_token_storage.py:237`, `upstream_oauth/secret_reencryption.py:80` and
  `valkey/live_log_publisher.py:56`. Verify with `test_dep9_failed_reencryption_logs_its_cause` (the
  `token_encryption.reencrypt_failed` line carries an `exception` field and neither the old nor the new ciphertext) and
  with the existing live log tests (the publisher's own failure line does not re-enter the buffer)
- [x] 3.5 Add one sentence on exception rendering to the logging section of `docs/self-hosting/configuration.md`, under
  `BUNDLEMCP_LOG_FORMAT`. Verify with `python3 tools/check_docs_links.py` and `python3 tools/check_docs_settings.py`

## 4. Server writes on the entity

- [x] 4.1 Add the frozen `ServerChanges` value object in `domain/servers/server_changes.py`, every field described,
  with `None` meaning "keep the stored value". Add `McpServer.register(name, changes)` and
  `McpServer.reconfigure(changes)` with today's rules: the `send_identity_header` default from `is_internal_host`, an
  empty `static_headers` keeping the stored headers, the auth mode settled from the stored headers, and `None` keeping
  `send_identity_header`, `protocol_mode` and `listing_snapshot`. Verify with domain tests in
  `tests/domain/test_mcp_server_changes.py`: `test_ups1_auth_mode_follows_the_stored_headers`,
  `test_ups1_oauth_and_delegated_modes_are_kept`, `test_ups3_empty_static_headers_keep_the_stored_ones`,
  `test_ups13_identity_header_defaults_by_host` and `test_ups10_omitted_fields_keep_their_stored_value`
- [x] 4.2 Add `ServerUpsert.changes() -> ServerChanges`. Reduce `ServerService.upsert` to the lookup, the
  self-reference check, `register` or `reconfigure`, the policy and grant checks, the save and the probe decision.
  Verify with the unchanged `tests/application/test_management_on_fakes.py`,
  `tests/application/test_server_setup_on_fakes.py` and API server tests, and with `uv run lint-imports` (the domain
  imports no application type)

## 5. `session` replaces `legacy` (UPS-10)

- [x] 5.1 Add `domain/servers/protocol_mode.py` with `NegotiationMode` (`auto`, `session`), `PinnedRevision` and
  `ProtocolMode`. Type `McpServer.protocol_mode`, `DiscoveryInputs.protocol_mode`, `ServerChanges.protocol_mode` and
  `ServerRead.protocol_mode` with it, and rewrite their descriptions without `legacy`. Verify with
  `test_ups10_named_modes_and_revisions_validate` (auto, session and a date pass) and
  `test_ups10_unknown_modes_are_rejected_by_the_domain` (`newest` and `legacy` fail at the domain)
- [x] 5.2 Type `ServerUpsert.protocol_mode` as `ProtocolMode | None`, with a `mode="before"` validator that maps
  `legacy` to `session`, and a description that names `legacy` as a deprecated alias. Verify in `tests/api/` with
  `test_ups10_legacy_alias_is_stored_and_read_as_session`, `test_ups10_invalid_mode_is_rejected` (422 for `newest`)
  and `test_ups10_openapi_lists_named_modes_as_an_enum` (the enum is `auto` and `session`, the pattern is kept,
  `legacy` is absent)
- [x] 5.3 Add `infrastructure/fastmcp/connect_mode.py` with `connect_mode(mode)`, mapping `session` to the SDK's
  `"legacy"`, and call it in both `GuardedClientFactory` constructors. Verify with
  `test_ups10_session_mode_connects_through_the_handshake` against the loopback upstream. Move the tests that use
  `protocol_mode="legacy"` (`test_upstream_session_pooling.py`, `test_pooled_upstream_sessions.py`, `test_mrtr.py`,
  `test_relay.py`, `test_member_notifications.py`, `test_inspector.py`, `test_discovery.py`,
  `test_management_on_fakes.py` and `test_server_setup_on_fakes.py`) to `session`, keeping one API test on the alias.
  Fixtures that write an `McpServerRow` directly keep `legacy`, because that is the column's stored spelling in this
  release (5.4); entities, API bodies and client factories use `session` and `connect_mode`
- [x] 5.4 In `SqlAlchemyServerRepository`, write `session` to the row as `legacy` and read `legacy` from a row as
  `session`. Update the `McpServerRow.protocol_mode` description to say the column holds the handshake mode's
  pre-rename spelling until the contraction. Verify with `test_ups10_stored_spelling_stays_readable_one_release_back`
  in `tests/infrastructure/test_rows.py` (an entity with `session` is stored as `legacy`, and a stored `legacy` loads
  as `session`) and with `test_ups10_server_stored_before_the_rename_reads_as_session` through the API
- [x] 5.5 Verify bootstrap, import and export with `test_ups10_bootstrap_document_may_use_the_legacy_alias` in
  `tests/infrastructure/test_bootstrap.py` and `test_ups10_export_says_session` in `tests/api/test_config_transfer.py`
- [x] 5.6 Run `cd apps/web && npm run openapi`. In `components/ServerRegistration.vue` and
  `pages/upstreams/[name].vue`, replace the `legacy` option with `session — always the initialize handshake`, and
  type the mode refs from the generated `components["schemas"]` types. Verify with `npm run typecheck` and
  `npm run build`
- [x] 5.8 Verify that the upstream list shows a `session` badge for a session-mode server: `utils/protocolLabel.ts`
  prints any mode other than `auto` verbatim as the badge, and the API tests show reads return `session`. Verified by
  reading the component and the API tests, not by a click-through on the compose stack (the local stack runs the
  previous images)
- [x] 5.7 Replace `legacy` with `session` (naming `legacy` as a deprecated alias) in `docs/manage/servers.md`,
  `docs/guide/upstream-server-settings.md` and `docs/connect/stdio-sidecar.md`, in the Notes entity list of
  `openspec/specs/architecture/spec.md`, and in `tests/conformance/run_conformance.py`. Verify with
  `python3 tools/check_docs_links.py`, `python3 tools/check_docs_symbols.py` and
  `grep -rn -A3 protocol_mode docs`, where `legacy` appears only as the deprecated alias

## 6. Gates

- [x] 6.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .` and `uv run lint-imports` (delete
  `.import_linter_cache` first), then `python3 tools/check_docs_links.py`, `check_docs_symbols.py`,
  `check_docs_settings.py`, `check_adr_graph.py` and `check_compose_ports.py`, then `python3 tools/check_spec_ids.py`,
  `cd apps/web && npm run openapi` (DTOs changed: `git diff --exit-code apps/web/openapi.json apps/web/types/api.d.ts`
  is clean after it), and `openspec validate --all --strict`. All pass
