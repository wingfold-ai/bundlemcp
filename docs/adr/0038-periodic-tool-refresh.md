# ADR-0038: A periodic sweep keeps the tool cache current

**Status:** accepted · **Date:** 2026-09-22 · **Extends:** [ADR-0012](0012-per-call-upstream-connections.md)

## Context

Endpoints serve `tools/list` from the Postgres tool cache ([DISC-4](../../spec/11-tool-discovery.md)), so the cache is
what clients see. It was written on three events only: a server being created or updated, an explicit "refresh tools",
and an upstream OAuth connect. Nothing re-read an upstream after that.

A deployment hit the gap on day one. Two upstreams were registered while their containers were not running yet.
Discovery failed on DNS, twice, below the three consecutive failures that turn `health_status` to `error`, so both
stayed `unknown` with zero cached tools. Once the containers came up, the gateway talked to them live for prompts and
resources, yet their tools never appeared, and nothing in the UI said anything was wrong. A manual refresh fixed it.

The spec named two more triggers that would have caught this, and neither can fire:

- Opportunistic discovery "whenever the gateway performs a live `tools/list`" was carried over from metamcp, which fans
  `tools/list` out to every upstream. bundlemcp answers from the cache, so there is no live `tools/list` to ride on.
- Upstream `tools/list_changed` ([PROT-10](../../spec/32-protocol-passthrough.md)). Per-call upstream connections
  (ADR-0012) are closed between calls, so a notification sent then never arrives, and one relayed during a call is
  passed through to the client without re-discovering.

## Decision drivers

- A server registered before its upstream is reachable must get its tools without an operator noticing and intervening.
- The cache must converge on upstream reality within a bounded time, whatever the upstream does or does not announce.
- Any number of gateway replicas; the work must not multiply by the replica count, and no replica may be special.
- Serving stays write-free and upstream-free on the hot path (DISC-2, DISC-4).

## Decision

- Every replica runs a `ToolRefresher` loop that wakes every `BUNDLEMCP_DISCOVERY_REFRESH_INTERVAL` seconds (default
  1800; `0` disables it) and calls `DiscoveryService.discover_all()`, which runs the ordinary discovery for every
  registered server, one after another ([DISC-7](../../spec/11-tool-discovery.md)).
- Before sweeping, a replica takes a Valkey lease through the existing `RefreshLock` contract (`SET NX` with an expiry).
  The lease is never released; it expires about a tenth of an interval before the next tick. A replica that finds it
  held skips its tick, so one replica sweeps per interval without electing a leader.
- A sweep is the same discovery as every other trigger: hash-gated writes, capability snapshot, `list_changed` announced
  to live clients when the tool set moved, and failures counted toward `health_status`. One server's failure is logged
  and skipped; it never ends the sweep. A server waiting for its first upstream OAuth connection is not a failure.
- The first sweep runs one interval after start, not at boot, so a rolling restart does not stampede the upstreams.
- Every discovery probe, from any trigger, is bounded to 60 seconds. Before this the probe relied on the MCP client's
  transport defaults, and one hanging upstream would have held up the sweep of every server after it. A timeout is an
  ordinary discovery failure.
- The unreachable opportunistic trigger is removed from DISC-1 and recorded in the spec's decision log.

## Alternatives considered

- **Retry only failed discoveries, with backoff.** Heals the case that prompted this, but not an upstream whose tools
  change silently between calls, and it needs per-server retry state shared across replicas. The sweep covers both with
  no new state.
- **Make `tools/list` fan out to upstreams, as metamcp does.** Would make the opportunistic trigger real, at the cost of
  an upstream round trip per server on every client listing and of availability coupling that DISC-4 exists to avoid.
- **Persistent upstream connections to receive `list_changed`.** The proper fix for PROT-10, deferred with connection
  pooling (ADR-0012); much larger than this change and still blind to upstreams that never send the notification.
- **A dedicated scheduler process or leader election.** Adds a deployable or a coordination protocol for a job that
  tolerates an occasional skipped or doubled run; a self-expiring lease is enough.

## Consequences

### Positive

- A server registered before its upstream was up heals within one interval, without anyone noticing it was broken.
- An upstream that stays unreachable reaches `health_status: error` after three sweeps instead of sitting at `unknown`
  indefinitely.
- Tool changes that nobody announced reach clients within one interval, through the existing BND-7 invalidation.

### Trade-offs

- Every upstream gets one `initialize` + `tools/list` per interval, from one replica, whether or not anything changed.
  At the default of 30 minutes this is negligible; a deployment with hundreds of servers may want a longer interval.
- Freshness is bounded by the interval, not immediate; the manual refresh remains for when an operator does not want to
  wait.
- A sweep runs servers sequentially, so a slow upstream delays the rest of that sweep by up to the 60-second probe
  timeout. A sweep outlasting its lease at worst lets the next tick start a second, overlapping sweep, which the
  hash-gated writes make harmless.
- The consecutive-failure counter behind `health_status` is still kept per replica in memory, so with several replicas
  the three failures that flip a server to `error` may take longer than three intervals to accumulate on one replica.
