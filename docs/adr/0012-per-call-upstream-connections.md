# ADR-0012: Per-call upstream connections in v1; pooling deferred

**Status:** superseded by [ADR-0054](0054-upstream-session-pooling.md) · **Date:** 2026-07-02 · **Amended by:**
[ADR-0030](0030-fastmcp-4.md)

## Context

metamcp maintained pre-warmed idle/active upstream connection pools — a major complexity source (generation counters,
health timers, invalidation races) that still didn't survive restarts. Spec SES-8 already says "no pre-warming
complexity in v1; measure cold-start first".

## Decision drivers

- Correctness first: per-call connections make identity isolation trivially right (AUTH-31 — forwarded credentials can
  never leak across callers).
- The performance requirement is a *measured budget* (OPS-13: ≤50 ms p95 added latency); optimizing before the
  integration suite can measure it is guesswork.
- Pooling identity-free upstream sessions can be added behind the same client-factory seam without touching the endpoint
  edge.

## Decision

v1 opens a **fresh upstream client per tools/call** (connect → call → close). The session record still tracks bindings
(SES-6 bookkeeping), and server config changes invalidate via invalidation events, but no live connection is reused
across calls yet.

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- No pool invalidation races; drastically simpler failure handling.

### Trade-offs

- Per-call initialize round-trip to upstreams; stateful upstreams see short-lived sessions. Revisit against the OPS-13
  measurement — this ADR is expected to be superseded by a pooling ADR when the data says so.

