# Design

## Context

See [proposal.md](proposal.md) for the motivation. Today `DiscoveryService` (application) keeps
`self._failures: dict[uuid.UUID, int]`, compares it with a constructor argument defaulting to `DEFAULT_MAX_ATTEMPTS`,
and is the only writer of `health_status`. `RuntimeConfig` (application/serving) already reads runtime keys with a
per-replica cache invalidated by invalidation events; `server_error_attempts` is registered in
`domain/config/config_registry.py` and read by nothing. Tool calls end in `ToolCall.finish` (api/mcp/tool_call) with a
`CallOutcome` that does not say whether the upstream was unreachable or answered with a JSON-RPC error. `ToolRefresher`
(api/jobs) shows the lease pattern a poller would reuse.

## Goals / Non-Goals

**Goals:**

- One shared, atomic failure streak per server, in Valkey.
- One component that turns "a connect to server X failed / succeeded" into health transitions, used by every source
  (discovery, live calls, polling, later SES-7).
- No Postgres write on the hot path unless the health status actually changes.

**Non-Goals:**

- Circuit breaking (refusing calls to a server in `error`). Health is reported, not enforced.
- Changing `connection_state` (UPS-12) semantics; it stays discovery-owned.

## Decisions

### A failure-streak contract in live state

`application/contracts/live_state/failure_streak.py`: `@runtime_checkable` protocol `FailureStreak` with
`record_failure(server_id) -> int` (returns the new count) and `reset(server_id) -> None`. The Valkey adapter
(`infrastructure/valkey/failure_streak_store.py`) uses `INCR` plus `EXPIRE` (24 h, refreshed on each failure) on
`bundlemcp:health:streak:{server_id}` and `DEL` on reset. An in-memory fake goes in `infrastructure/memory/`.

*Alternative:* a counter column on the server row. Rejected: every failed call would become a Postgres write under a
row lock, and the count is live state, which the state model puts in Valkey.

### One health reporter for every source

`application/discovery/upstream_health.py`: `UpstreamHealth` takes a `UnitOfWorkFactory`, the `FailureStreak` and
`RuntimeConfig`. `failed(server, error)` increments the streak and, when the count reaches
`server_error_attempts` and the server is not already `error`, writes `health_status=error` and `last_error` in its own
short unit of work and logs `discovery.server_marked_error`. `succeeded(server)` resets the streak and writes
`ok` only when the server's current status is not `ok`. `DiscoveryService` drops its dict and its `max_attempts`
argument and calls the reporter; its `discovery.failed` warning keeps the attempt number from the returned count.

### Live calls report through the settlement step

`UpstreamCall` (api/mcp/tool_call) marks a `CallOutcome` with `connection_failed=True` when the exception is a
transport failure (connect error, TLS error, non-MCP HTTP status, dropped stream); a timeout, a cancellation, a
`NeedsConnect`/401 and a JSON-RPC error from the upstream leave it false. `ToolCall.finish` then calls
`UpstreamHealth.failed` when `connection_failed`, `succeeded` when `outcome.reached_upstream`, and nothing otherwise.
`succeeded` reads the status from the `BundleView`'s server snapshot first, so a healthy server costs one Valkey `DEL`
and no Postgres access. The reporter call is wrapped so a Valkey failure is logged and never fails the call.

*Alternative:* report from the `tools/call` handler. Rejected: the settlement step already sees the outcome and is the
Pipes-and-Filters stage for after-call accounting.

### The threshold is read per failure

`UpstreamHealth` reads `server_error_attempts` from `RuntimeConfig` on each counted failure, so a config change applies
on the next failure without restart, within the propagation budget (SES-19). Values below 1 are rejected by adding
`ge=1` validation for this key in the config registry.

### Polling reuses the lease pattern (only if UPS-9 is built)

`api/jobs/health_poller.py` mirrors `ToolRefresher`: every replica ticks, one takes the lease
`bundlemcp:health:poll`. The interval and enable flag are runtime keys (`health_poll_enabled`, `health_poll_interval`)
read at each tick, so the loop runs on every replica but does nothing while disabled. A poll is a bounded connect
(`initialize` or `server/discover` per UPS-10, 10 s) through the existing `UpstreamProbe`, without `tools/list`, and
reports to `UpstreamHealth`. Upstream-OAuth servers without a connected account are skipped as in UPS-17.

## Risks / Trade-offs

- [A burst of concurrent failed calls flips health on its first few calls] → That is the semantics of a shared
  consecutive count; with the default of 3 a dead upstream is reported within three calls, which is the point.
- [Interleaved success and failure from different replicas reset each other] → Accepted: "consecutive" is defined over
  the order Valkey sees; a flapping upstream stays `ok`, which matches metamcp's tracker.
- [Valkey down] → Counting is skipped and logged (fail-open); health is not updated until Valkey is back. Calls are
  unaffected.
- [Polling adds upstream traffic] → Off by default; the interval floor is 30 s.

## Migration Plan

No data migration. On deploy, in-process counts are lost once (as on any restart today); the shared count starts at
zero. Rollback is a revert; the Valkey keys expire on their own.
