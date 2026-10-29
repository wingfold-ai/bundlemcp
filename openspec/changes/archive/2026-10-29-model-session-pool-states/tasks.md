# Tasks

## 1. Characterise the pool before touching it

- [x] 1.1 In `tests/infrastructure/test_pooled_upstream_sessions.py`, add
  `test_ses8_concurrent_leases_get_separate_sessions`. Two leases held at once under one key open two upstream
  sessions, both are kept idle afterwards, and a third call reuses one of them. Verify by asserting
  `recording.initializes() == 2` and `len(pool.held) == 2`, and that the test passes on the unchanged pool
- [x] 1.2 Add `test_ses8_a_lowered_cap_closes_idle_sessions_above_it`, with a limits callable the test changes:
  - Lowering `per_server` leaves exactly the cap of sessions on that server, LRU and shared first.
  - Lowering `total` then trims across servers.
  - A bound session evicted this way is not `DELETE`d upstream.

  Verify against `pool.held` and `recording.deletes()` after awaiting `pool._close_idle(...)` directly, so no timing
  is involved
- [x] 1.3 Add three end and invalidation tests:
  - `test_ses4_ending_a_binding_while_leased_closes_on_release`: `end` during a lease keeps the lease working; the
    session is gone from `pool.held` after release.
  - `test_ses21_invalidating_twice_while_leased_closes_once`: the transport is closed once and no error is logged.
  - `test_ses7_a_lease_ending_in_an_error_is_not_reused`: an exception inside `lease` drops the session, and the next
    call initializes again.

  Verify all three pass on the unchanged pool
- [x] 1.4 Add `test_ses9_closing_the_pool_while_leased_lets_the_lease_end`. `pool.close()` during a held lease, then
  leaving the lease, raises nothing and leaves `pool.held` empty. Verify it passes on the unchanged pool
- [x] 1.5 Add `test_auth31_a_fixed_header_transport_is_keyed_by_its_headers`. It uses a plain factory: a callable
  wrapping `GuardedClientFactory.__call__`, so it is not a `LeaseAwareClientFactory`. Equal headers reuse a session,
  different credentials open another, and closing an idle shared session sends no `DELETE` of the pool's own. Verify
  with `recording.initializes()` and `recording.deletes()` on the unchanged pool. Found while characterising: such a
  transport ends its own session as it closes (the SDK's terminate-on-close), so the test asserts exactly one
  `DELETE` per closed session rather than none

## 2. Session state machine

- [x] 2.1 Create `infrastructure/fastmcp/pooled_session.py` with `SessionState` (`LEASED`, `IDLE`, `RETIRING`,
  `CLOSED`), `IllegalSessionTransition` and `PooledSession`, moved from the pool module. Give `PooledSession` the
  following:
  - the transition methods `checkout()`, `release()`, `retire()` and `close()`
  - the properties `is_open`, `evictable` and `ends_upstream_on_eviction`
  - a `state` field described like every other field

  Remove `in_use`, `connected` and `stale`. Verify with a new `tests/infrastructure/test_pooled_session.py` that
  asserts every cell of the transition table in design.md, including that illegal cells raise
- [x] 2.2 Switch `PooledUpstreamSessions` to the state methods. Make these changes:
  - `_checkout` filters on `state is IDLE`.
  - `_release` closes `RETIRING` or unpooled sessions.
  - `end` and `_invalidate` call `retire()`.
  - `_close` calls `close()`.
  - `_listen` and `relisten` read `is_open`.
  - `_connect` assigns `session.client` only after `__aenter__()` succeeds.

  Verify that the group 1 tests and the existing pool tests in `tests/infrastructure/` and `tests/api/` (pooling,
  member notifications) pass unchanged, and that `grep -n "in_use\|\.stale\|\.connected" pooled_upstream_sessions.py`
  is empty

## 3. Transport strategy, eviction helpers, typed lease

- [x] 3.1 Add the `LeaseTransport` protocol and `lease_transport_for(factory)` in
  `infrastructure/fastmcp/lease_transport.py`, with `SlotLeaseTransport` and `FixedHeaderLeaseTransport` in their own
  modules. The pool calls `lease_transport_for` once in `__init__`, and uses it in `_variant`, `_connect`, `end` and
  `_close`. Verify that `grep -rn "isinstance(self._factory" infrastructure/fastmcp` is empty, and that tests 1.5 and
  `test_ses4_ending_a_binding_deletes_its_upstream_session` pass
- [x] 3.2 Add `_evict(session, *, end)` and `_trim_to(cap, within)`. Replace the nine remove-then-close sites, and
  rebuild `_make_room` and `_close_idle` on `_trim_to` as design.md orders them. Verify that tests 1.2 and the
  existing `test_ses8_*` tests pass, that `grep -c "_sessions.remove" pooled_upstream_sessions.py` returns 1, and that
  `uvx radon cc -s` ranks no method of the module worse than B
- [x] 3.3 Type the remaining fields:
  - `PooledLease.client` as `Client`, a property over `session.client` (design.md says why not a field)
  - `PooledLease.pool: Any` replaced by `relisten: Callable[[PooledSession], None]`
  - `_spawn`'s argument as `Coroutine[Any, Any, None]`

  Verify with `uv run ruff check .`, the pool and member-notification tests, and
  `uvx radon mi -s pooled_upstream_sessions.py` reporting grade A

## 4. Composition root

- [x] 4.1 Characterise first. Add `tests/api/test_composition_lifecycle.py::`
  `test_ses10_ops5_background_jobs_run_while_serving_and_stop_with_the_app`, which checks the job tasks named by
  `InvocationSweepJob`, `SessionSweepJob` and `AuditPurger` exist while `serving(...)` is open and are gone after.
  Also add `test_ops9_stream_and_audit_queue_gauges_are_exported` to `tests/api/test_metrics_route.py`:
  `bundlemcp_open_streams` and `bundlemcp_audit_queue_depth` appear in the composed app's `/metrics`. Verify both
  pass on the unchanged code
- [x] 4.2 Add `main/background_job.py` (`BackgroundJob` protocol) and `CompositionRoot._run(job)`. Use `_run` for the
  seven synchronous jobs, `_start_oidc_provider` included. Verify that
  `grep -c "self._stack.callback(.*\.stop)" composition_root.py` drops to 2 (`drain.stop`, which has no `start`, and
  the `job.stop` line inside `_run` itself), and
  that test 4.1 and `test_ses10_app_shutdown_stops_the_sweeper` pass
- [x] 4.3 Extract `_open_engine`, `_call_tracer`, `_open_redis`, `_upstream_sessions`, `_metering_hook`,
  `_start_tool_refresher` and `_start_secret_reencryption`, called in today's order and reading `self._settings`
  directly. Verify the following:
  - `uvx radon cc -s main/composition_root.py` ranks `_compose` C or better.
  - `grep -c "settings = self._settings" composition_root.py` is 1.
  - `test_dep9_the_job_runs_only_with_keys_and_an_interval`, `tests/api/test_tracing.py` and
    `tests/api/test_http_metering.py` pass.
- [x] 4.4 Build `InProcessStreamRegistry` before `PrometheusMetrics`. Replace the `audit_queue_depth` constructor
  argument with `PrometheusMetrics.observe_audit_queue(depth)`, called right after `QueuedAuditWriter` is built.
  Update `tests/infrastructure/test_prometheus_metrics.py` to use the method, and assert that the gauge reads 0 before
  it is called. Verify that this test and test 4.1's gauge test pass
- [x] 4.5 Type `_server_change(upstream_sessions: UpstreamSessionPool)` and
  `_config_refresh(runtime_config: RuntimeConfig)` as returning `Callable[[InvalidationEvent], Awaitable[None]]`, with
  the inner `event` parameter annotated. Verify with `uv run ruff check .`, `uv run lint-imports`, and
  `test_ses9_ses21_ups6_a_header_change_closes_another_replicas_transports`

## 5. Gates

- [x] 5.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .` and `uv run lint-imports` (delete
  `.import_linter_cache` first, since modules moved). Run `python3 tools/check_docs_links.py`,
  `check_docs_symbols.py`, `check_docs_settings.py`, `check_adr_graph.py` and `check_compose_ports.py`. Then run
  `python3 tools/check_spec_ids.py` and `openspec validate --all --strict`. All pass. No DTO or route changed, so
  `npm run openapi` is not needed
