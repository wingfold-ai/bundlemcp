# Design

## Context

See [proposal.md](proposal.md) for why. This section covers the current code the refactor has to preserve. Line
numbers are as of `main` at 2399dae.

**The pool.** `PooledUpstreamSessions` (infrastructure, `infrastructure/fastmcp/pooled_upstream_sessions.py`) holds
`PooledSession` models in a list guarded by one `asyncio.Lock`. A session's lifecycle is spread over four booleans
(lines 99-110):

- `pooled`: fixed at checkout. It is False when the session was opened past a cap.
- `in_use`: set at checkout (310), cleared at release (488).
- `connected`: set after `client.__aenter__()` (384), cleared in `_close` (507). `_listen` reads it as its loop
  condition (417), and so does `relisten` (396).
- `stale`: set by `end` (255) and `_invalidate` (287). It closes the session on release (492).

Three facts follow from the code and are not written down anywhere:

- An idle session in the list is never stale. `end` and `_invalidate` remove an idle session the moment they mark it.
- An idle session always has a client. A failed connect raises inside `lease`, which discards the session.
- `close()` (273) closes sessions that are still leased. Their later `_release` then finds them closed.

The factory decides how a transport takes headers:

- A `LeaseAwareClientFactory` reads each lease's headers from a `LeaseSlot`, and ends upstream sessions with `DELETE`.
- A plain `UpstreamClientFactory` has the headers fixed at build time, so they become part of the key (`_variant`), and
  the pool never ends upstream sessions through it. Its transport ends its own session as it closes (the SDK's
  terminate-on-close), so each closed session still receives exactly one `DELETE`, none of them from the pool.

The plain path is live. The composition-root tests in `tests/api/` pass plain factories through
`CompositionOverrides.client_factory` with pooling on, which is the default.

Remove-then-close appears at lines 257, 289, 307, 355, 493, 499, 549, 559 and 565. The `end` flag differs by caller:

| Caller | `end` |
|---|---|
| `end` | False: `end` deletes upstream itself |
| fresh checkout | False: the session already expired |
| `_invalidate`, `_release` | True |
| `_discard` | its caller's choice |
| evictions | `bound_to is None` |

**The composition root.** `CompositionRoot._compose` (main, `main/composition_root.py:162-454`) has radon complexity D
(25). Most of the branches are `overrides.x or default` and the acquisitions behind `if`s: engine, tracing, Valkey,
pooling, metering, refresher and re-encryption. Seven background jobs repeat `start()` followed by
`self._stack.callback(stop)`:

- `TokenPurger`
- `ToolRefresher`
- `SecretReencryptionJob`
- `InvocationSweepJob`
- `SessionSweepJob`
- `AuditPurger`
- `DiscoveringOidcProvider`, in `_start_oidc_provider`

Each has a synchronous `start()` and a synchronous `stop()`. No `BackgroundJob` protocol exists yet.

The Prometheus gauges at 227-231 close over `registry` (247) and `audit` (234) before either exists. `registry` has no
dependencies. `audit` cannot simply be built first, because `QueuedAuditWriter(sessions, metrics)` needs the metrics:
the dependency is a genuine cycle. `_server_change` and `_config_refresh` (529-543) have no annotations.
`.claude/docs/local-aliasing.md` documents the `settings`/`overrides` aliases at the top of `_compose` as the one
allowed exception, on the condition that they appear in one method only.

## Goals / Non-Goals

**Goals:**

- Every pool behaviour observable today stays the same, and characterisation tests pin it before the refactor:
  - which session a request gets
  - which sessions are evicted, and in what order
  - which closes end the upstream session (`DELETE`)
  - how notifications reach the sink
- `_compose` drops to radon grade C or better. The teardown order of the exit stack stays exactly the same.
- No layer moves. The pool pieces stay in infrastructure; `BackgroundJob` lives in `main/`.

**Non-Goals:**

- Typing the notifications the pool forwards. That is change `type-upstream-notifications`.
- `ServerCapabilities` for `_listen_filter` (audit finding S9).
- Changing the `UpstreamSessionPool` or `UpstreamLease` contracts in `application/contracts/upstream/`. They keep
  `client: Any`, because the application layer cannot name the SDK client.
- Splitting `_compose` into wiring phases that pass a dozen collaborators to each other. The wiring stays flat, as the
  documentation allows.

## Decisions

### A `SessionState` enum, changed only through `PooledSession` methods

`SessionState` and `PooledSession` move to a new module, `infrastructure/fastmcp/pooled_session.py`. `SessionState` is
a `StrEnum` with four members:

- `LEASED`: a lease holds the session. The transport may not be open yet.
- `IDLE`: open, with no lease.
- `RETIRING`: leased, but its configuration changed or its binding ended, so it is closed when the lease ends.
- `CLOSED`: the transport is closed. The session is never handed out again.

The transitions, as methods on `PooledSession`:

| From → event | `checkout()` | `release()` | `retire()` | `close()` |
|---|---|---|---|---|
| `LEASED` | illegal | `IDLE` | `RETIRING` | `CLOSED` |
| `IDLE` | `LEASED` | illegal | `RETIRING` | `CLOSED` |
| `RETIRING` | illegal | stays `RETIRING` | stays `RETIRING` | `CLOSED` |
| `CLOSED` | illegal | stays `CLOSED` | stays `CLOSED` | stays `CLOSED` |

An illegal transition raises `IllegalSessionTransition`, a `RuntimeError` subclass defined in the same module. It never
uses `assert`, because the audit's finding S12 shows how asserts disappear under `-O`. `CLOSED` absorbs `release()`
and `retire()` because `close()` legitimately closes leased sessions at shutdown.

The new state replaces three of the booleans:

- `in_use` becomes `state in {LEASED, RETIRING}`.
- `stale` becomes `state is RETIRING`.
- `connected` becomes the property `is_open`, which is `client is not None and state is not CLOSED`. To make that
  exact, `_connect` assigns `session.client` only after `__aenter__()` succeeds. The behaviour is unchanged: today a
  failed `__aenter__` leaves `connected` False, so `_close` returns early without calling `__aexit__`. With the
  client unassigned, the same early return happens.

`evictable` becomes `state is IDLE and not subscriptions`. `pooled` stays a constructor field. It says whether the
session counts toward the caps, which never changes, so it is not a stage of the lifecycle. `close()` is called inside
`_close` (the spawned task), not at eviction, so the moment `_listen` stops looping is the same as today.

*Alternative:* add a `NEW` state for a session leased before its transport is open. Rejected: `client is None` already
distinguishes it, and a retired session can be new too. That would double the states.

*Alternative:* a generic state-machine library. Rejected: four states and four events fit in one table. A dependency
would add more than it saves.

### A `LeaseTransport` strategy, chosen once

`infrastructure/fastmcp/lease_transport.py` defines the `LeaseTransport` protocol with three methods:

- `variant(request) -> str | None`
- `open(server, slot, *, continues, handlers) -> Client`
- `async end_session(server, session_id, protocol_version, headers) -> None`

The same module holds `lease_transport_for(factory)`, the only place the `isinstance(…, LeaseAwareClientFactory)`
check remains. It sits beside the protocol, following `.claude/docs/module-naming.md` on factories. There are two
implementations, each in its own module named for its mechanism:

- **`SlotLeaseTransport`** reads the headers from the lease slot on every request. Its `variant` is None. `open`
  calls `for_lease(…, auto_initialize=not continues)`, and `end_session` delegates to the factory.
- **`FixedHeaderLeaseTransport`** has the headers fixed into the transport. Its `variant` is today's SHA-256 over the
  sorted headers. `open` calls the factory with `slot.headers` and a `SlotResponseLog`, and `end_session` does
  nothing.

`PooledUpstreamSessions.__init__` keeps its signature and calls `lease_transport_for(factory)` once. The composition
root and every test go on constructing the pool as before.

*Alternative:* let the composition root choose the transport and pass it in. Rejected for now: every test that builds
the pool would change, and nothing outside the pool needs to know. The chooser can move later without touching the
strategies.

### `_evict` and `_trim_to`

- **`_evict(session, *, end)`** removes the session from the list if it is there, then spawns `_close`. It replaces all
  nine sites. Each caller passes its `end` value from the table in Context, so `end`'s semantics are unchanged.
  `PooledSession.ends_upstream_on_eviction` (`bound_to is None`) names the rule for evictions in one place.
- **`_trim_to(cap, within)`** evicts `_eviction_candidate` among the sessions matching `within` until at most `cap` of
  them remain. It returns False when nothing is evictable.
- **`_retire(session, *, end)`** is the step `end` and `_invalidate` share: an idle session is evicted at once, as
  today, and a leased one is `retire()`d, so its release closes it. An idle session is never left `RETIRING`.
- **`_checkout`** splits into `_reuse` (lease a matching idle session) and `_open` (build a new one, making room
  first). The state filter alone left it at radon C (12); the split brings every method of the module to B or better.

The callers become:

- `_make_room` is `_trim_to(total - 1, everything) and _trim_to(per_server - 1, on_server)`. Today's loop evicts
  globally while the replica is at the total cap, and only then per server. The two calls run in that order, and the
  `and` short-circuit keeps today's early `False`.
- `_close_idle` keeps its idle-timeout pass. It then calls `_trim_to(per_server, on that server)` for each server,
  followed by `_trim_to(total, everything)`.

*Alternative:* trim per server first in `_make_room`. Rejected: when both caps are full, that order evicts one session
where today's evicts two. That is arguably better, but it changes which sessions survive.

### Typed lease fields

`PooledLease.client` becomes `Client`. The lease is yielded only after a successful connect, so the client is never
None there. It is a read-only property over `session.client`, not a field: a Pydantic field typed `Client` would
validate with `isinstance`, and the plain-factory path accepts any object a factory returns today (the `_Failing`
client in `tests/api/test_server_setup_api.py` is one), so a field would turn a working lease into a
`ValidationError`. The property raises `RuntimeError`, never `assert`s, if it is ever read without a client.
`PooledLease.pool: Any` becomes `relisten: Callable[[PooledSession], None]`: `relisten` is the only part of
the pool the lease uses, and a forward reference to `PooledUpstreamSessions` would need a `model_rebuild()`. `_spawn`
takes a `Coroutine[Any, Any, None]`.

### `CompositionRoot._run` over a `BackgroundJob` protocol

`main/background_job.py` defines `BackgroundJob(Protocol)` with `start() -> None` and `stop() -> None`.
`_run(job: BackgroundJob) -> None` starts the job and pushes `job.stop` onto the stack straight away, so each job's
teardown keeps its position.

The jobs whose stop is a coroutine keep their explicit pairs: `QueuedAuditWriter`, `LiveLogPublisher`,
`ValkeySignalBus`, `InvalidationSubscriber` and the pool. They differ in shape, both sync and async starts, and in
shutdown order. A second helper used three times would hide that.

*Alternative:* put `BackgroundJob` in `application/contracts/`. Rejected: only `main/` consumes it, and the jobs live
in three different layers, so a contract would describe nothing those layers need.

### Phase methods for acquisitions, in the `_start_oidc_provider` pattern

Each branch that acquires a resource and registers its teardown becomes a private method that does exactly that and
returns what it built:

- `_open_engine() -> AsyncEngine`
- `_call_tracer(engine) -> CallTracer`
- `_open_redis() -> Redis`
- `_upstream_sessions(client_factory, runtime_config, notifications) -> UpstreamSessionPool`
- `_metering_hook() -> MeteringHook`
- `_start_tool_refresher(discovery, redis) -> None`
- `_start_secret_reencryption(cipher, units, redis) -> None`

`_compose` calls them in today's order, so the exit stack unwinds exactly as before. They read `self._settings` and
`self._overrides` directly and never copy the alias preamble. Rule 5 in `local-aliasing.md` forbids repeating it, and
that document's exception stays true as written.

`UpstreamNotificationRouter` is now constructed even when pooling is off. Its constructor only stores references, so
nothing observable changes.

### Metrics after their sources

`registry = InProcessStreamRegistry()` moves above `PrometheusMetrics`. It has no dependencies, and its teardown
(`close_streams`) is registered later, where it is today. For the audit cycle, `PrometheusMetrics` drops its
`audit_queue_depth` constructor argument. A new method, `observe_audit_queue(depth)`, called right after the writer is
built, points the existing gauge at the writer. Until then the gauge reads 0, which is today's default.

*Alternative:* keep the late-bound lambda and comment it. Rejected: the audit flagged exactly that. Anything that read
the gauge before the writer exists would get a `NameError` from the closure instead of 0. Today only the scrape order
prevents that.

### Typed invalidation callbacks

`_server_change(upstream_sessions: UpstreamSessionPool)` and `_config_refresh(runtime_config: RuntimeConfig)` both
return `Callable[[InvalidationEvent], Awaitable[None]]`, the type `InvalidationSubscriber.on_event` already takes.

## Risks / Trade-offs

- [Risk] An `IllegalSessionTransition` fires on a path the table missed, and turns a quiet edge case into a failed
  request. → Mitigation: characterisation tests cover the edge paths before the refactor:
  - concurrent leases
  - `end` and invalidation while leased
  - `close()` while a lease is held
  - a lease ending in an exception
  - a lowered cap

  A pure table test asserts every cell.
- [Risk] Moving `client` assignment after `__aenter__` changes what `_close` sees after a failed connect. →
  Mitigation: that path returns early today too (`connected` is False). The characterisation test for an unreachable
  upstream (SES-7) stays green, and a new one asserts that a lease ending in an exception is not reused.
- [Risk] Reordering in `_compose` changes teardown order. Shutdown races would show up only under load. → Mitigation:
  each phase method registers its teardown at the point the inline code did. A new lifecycle test asserts that the
  named job tasks run while serving and are gone after exit.
- [Risk] Merge conflict with `type-upstream-notifications`. It edits `_listened`, `_handlers`, `_notify` and the
  `subscribe_resource`/`unsubscribe_resource` lines of `PooledLease`. This change edits `PooledLease`'s fields and the
  `self.pool.relisten` lines in the same two methods, plus `_listen`'s loop condition (`session.connected` →
  `session.is_open`). → Mitigation: land this change first, because it is structural and moves `PooledSession` out of
  the module. The notification change then rebases onto `is_open` and `self.relisten`, and its own edits stay inside
  the notification functions. If that change has merged first, this change's group 2 rebases instead, and only those
  lines conflict.
- [Trade-off] Three new small modules in `infrastructure/fastmcp/`. The module-naming rule prefers named modules over
  one large file, and the pool module drops by about a third.

## Migration Plan

None. This is an internal refactor with no stored data, configuration or API change. To roll back, revert the commit.
