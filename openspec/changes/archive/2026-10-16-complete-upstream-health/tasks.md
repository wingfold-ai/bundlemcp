# Tasks

## 1. Decide UPS-9

- [x] 1.1 Record the maintainers' choice for UPS-9 (build or retire) in the proposal; on "retire", delete the UPS-9
  delta and group 4 and state in the proposal that the ID stays unused; verify with
  `openspec validate complete-upstream-health --strict`

## 2. Shared failure streak and reporter (UPS-4)

- [x] 2.1 Add the `FailureStreak` contract, its Valkey adapter and in-memory fake; verify with infrastructure tests on
  fakeredis `test_ups4_streak_increments_atomically` and `test_ups4_streak_expires`
- [x] 2.2 Add `UpstreamHealth` reading `server_error_attempts` from `RuntimeConfig`, with `ge=1` validation on the key;
  verify with application tests `test_ups4_threshold_from_runtime_config` and `test_ups4_success_heals`
- [x] 2.3 Replace the dict and `DEFAULT_MAX_ATTEMPTS` in `DiscoveryService` with the reporter and wire it in
  `main/composition_root.py`; verify with `test_ups4_failures_on_two_replicas_add_up` (two services sharing one fake
  streak) and the existing UPS-4 tests
- [x] 2.4 Document the shared count and the config key in `docs/manage/servers.md` and
      `docs/self-hosting/configuration.md`; verify with `python3 tools/check_docs_settings.py` and
      `check_docs_symbols.py`

## 3. Live calls count (UPS-4) and sweeps add up (UPS-23)

- [x] 3.1 Classify transport failures on `CallOutcome` in `UpstreamCall`; verify with tests for connect error,
  timeout, cancellation, 401 and JSON-RPC error
- [x] 3.2 Report from `ToolCall.finish` to `UpstreamHealth`, never failing the call on a Valkey error; verify with API
  tests `test_ups4_live_call_failures_count` and `test_ups4_tool_error_is_not_a_connection_failure`
- [x] 3.3 Verify UPS-23 with `test_ups23_unreachable_upstream_marked_error_across_replicas` (three sweeps by two
  discovery services sharing one failure streak)

## 5. Gates

- [x] 5.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .` and `uv run lint-imports`; verify all
  pass with no new exceptions
- [x] 5.2 Run `python3 tools/check_docs_links.py`, `check_docs_symbols.py`, `check_docs_settings.py` and
  `check_adr_graph.py`; verify all pass
- [x] 5.3 Run `cd apps/web && npm run openapi` if a config DTO description changed; verify no stale diff
- [x] 5.4 Run `openspec validate --all --strict`; verify it passes
