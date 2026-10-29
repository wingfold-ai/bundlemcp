# Proposal

## Why

The 2026-10-29 code audit found two hotspots that are hard to change safely.

**The upstream session pool (finding S11).** `PooledUpstreamSessions`
(`infrastructure/fastmcp/pooled_upstream_sessions.py`, 566 lines) has the lowest maintainability index in the package.
Its problems:

- A session's lifecycle is spread over four booleans (`pooled`, `in_use`, `connected`, `stale`). Legal combinations are
  implied by the order of assignments.
- `isinstance(self._factory, LeaseAwareClientFactory)` chooses the transport behaviour at four call sites.
- The same remove-then-close step is written out nine times.
- The cap-trimming loop exists twice, once in `_make_room` and once in `_close_idle`.
- `PooledLease.client` and `PooledLease.pool` are typed `Any`.

No test leases two sessions at once, lowers a cap at runtime, or drives the plain-factory transport directly. So the
pool's riskiest behaviour has no characterisation.

**The composition root (finding S13).** `CompositionRoot._compose` (`main/composition_root.py`) has cyclomatic
complexity 25 (radon grade D). Its problems:

- `job.start()` followed by `self._stack.callback(job.stop)` is repeated seven times.
- The Prometheus gauge lambdas refer to `registry` and `audit` before either is defined. This works only because the
  lambdas run at scrape time.
- `_server_change` and `_config_refresh` have no type hints.

Flat wiring is allowed there (`.claude/docs/local-aliasing.md`), but the branches that acquire and tear down resources
are not wiring.

## What Changes

- A pooled session's lifecycle becomes one `SessionState` (leased, idle, retiring, closed), changed only through
  transition methods on `PooledSession`. `in_use`, `connected` and `stale` are removed. `pooled` stays as a fixed fact:
  it records whether the session counts toward the caps, and is not a stage of its lifecycle.
- The difference between a lease-aware client factory and a plain one moves into a `LeaseTransport` strategy, chosen
  once when the pool is constructed. The four `isinstance` checks are removed.
- One `_evict(session, *, end)` replaces the repeated remove-then-close step. One `_trim_to(cap, within)` serves both
  making room at checkout and enforcing a lowered cap.
- `PooledLease.client` is typed as the SDK `Client`. `PooledLease.pool` becomes a typed `relisten` callback.
- `CompositionRoot` gains `_run(job)` over a new `BackgroundJob` protocol. The branchy acquisitions move into phase
  methods that follow the existing `_start_oidc_provider` pattern: the database engine, the tracer, Valkey, the upstream
  session pool, the metering hook, the tool refresher and secret re-encryption.
- The stream registry is built before the metrics that read it. The audit-queue gauge is attached once the audit
  writer exists, through a new `PrometheusMetrics.observe_audit_queue(depth)`, because the writer itself needs the
  metrics.
- The two invalidation callbacks get types: `UpstreamSessionPool` in, and a `Callable[[InvalidationEvent],
  Awaitable[None]]` out.
- Characterisation tests land before each refactor. No behaviour changes, so the change carries no spec delta
  (`skip_specs`).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This is a behaviour-preserving refactor. SES-4, SES-5, SES-7, SES-8, SES-9, SES-21 and AUTH-31 (the pool) and
OPS-9 (the metrics) describe what stays the same, and the new tests cite them.

## Impact

- **Resolves:** audit findings S11 and S13 (2026-10-29). There is no GitHub issue.
- **Code:**
  - `infrastructure/fastmcp/pooled_upstream_sessions.py`
  - new `infrastructure/fastmcp/pooled_session.py` (`SessionState` and `PooledSession`, moved out of the pool module)
    and `lease_transport.py`, plus one module for each of the two transport strategies
  - `main/composition_root.py`
  - new `main/background_job.py`
  - `infrastructure/prometheus/prometheus_metrics.py`
- **Tests:**
  - `tests/infrastructure/test_pooled_upstream_sessions.py`
  - new `tests/infrastructure/test_pooled_session.py`
  - `tests/infrastructure/test_prometheus_metrics.py`
  - `tests/api/test_metrics_route.py`
  - new `tests/api/test_composition_lifecycle.py`
- **API:** none. No DTO or route changes, so `apps/web/openapi.json` is unaffected.
- **Docs:** none. No ADR: this implements ADR-0054's pool without changing any of its decisions. The `_compose` alias
  exception in `.claude/docs/local-aliasing.md` remains true as written.
- **Overlaps:** change `type-upstream-notifications` edits the same pool module: the notification dict conversion in
  `_listened`, `_handlers` and `_notify`, and the `subscribe_resource`/`unsubscribe_resource` lines in `PooledLease`.
  [design.md](design.md) gives the merge order.
- **Not covered:**
  - The notification typing, which belongs to `type-upstream-notifications`.
  - The capability-dict probing in `_listen_filter` (finding S9).
  - The optional `RequestContext.session` (finding S12).
  - The listing pager in `FastMcpUpstreamProbe` (finding N10). It is a sibling in `infrastructure/fastmcp/` and shares
    nothing with the pool.
