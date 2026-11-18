# ADR-0016: Protocol-relay design — per-replica registries + Redis signaling

**Status:** accepted · **Date:** 2026-07-02 · **Amended by:** [ADR-0027](0027-mcp-edge-method-handlers.md),
[ADR-0029](0029-dialects-and-dual-era-edge.md)

## Context

Spec 32 (ADR-0008, full-bidirectional proxy) requires relaying the whole MCP surface — progress, cancellation, and
server→client requests (sampling/elicitation) — while the state model (ADR-0004) forbids process-local state a request
depends on and pins live streams to one replica (SES-13). The tension: a cancel or an elicitation reply can arrive at a
different replica than the one holding the in-flight call or the client's event stream.

## Decision drivers

- The publish-only bus removes the hardest class of distributed bug (duplicate/missed delivery across a local fast path
  and a pub/sub path) at the cost of one sub-millisecond Redis hop.
- Keeping the pinned objects in a tiny registry — and everything else in Redis — preserves "any replica serves any
  request" (ARC-9): only the *live stream* is pinned, and the bus reaches it.
- Owning the endpoint edge (ADR-0011) made SSE responses and the GET stream a natural extension rather than a fight with
  FastMCP's server session manager.

## Decision

Two per-replica registries plus one Redis signaling layer (`gateway/streams.py`, `gateway/signals.py`):

- **StreamRegistry** holds the *only* replica-pinned objects SES-13 permits: GET-stream queues (by session), in-flight
  `CallHandle`s (by session + request id), and reply futures (by correlation id).
- **SignalBus** carries `cancel` / `deliver` / `reply` messages on a single `bmcp:signal:*` pattern subscription. It is
  **publish-only**: the publisher's own subscription is the delivery path too, so every signal is handled exactly once
  by whichever replica owns the target — no local-vs-remote dedup.
- **tools/call** returns `text/event-stream` when the client sent a `progressToken` (progress relayed as SSE, then the
  final result); otherwise the buffered JSON fast path. Timeouts follow PROT-2 (reset-on-progress + absolute cap) from
  runtime config (ADR: spec 33 invalidation).
- **Server→client requests** are delivered on the client's GET stream and the reply routed back by correlation id;
  handlers are attached to the upstream client only for capabilities the client advertised (PROT-5), bounded by the
  call's timeout (PROT-6).

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- Long-running calls work end to end: progress visible, cancellable, timeouts progress-aware — the motivating
  video-render case.
- Cross-replica correctness is proven hermetically (two app instances on one fakeredis: deliver/cancel/reply all route).

### Trade-offs

- SSE and the GET stream can't be tested through httpx's ASGITransport (it buffers whole responses), so relay tests run
  a real loopback uvicorn — still no Docker/network, but heavier than the ASGI-transport suite.
- **Known limit:** with per-call upstream connections (ADR-0012), an upstream `notifications/tools/list_changed` raised
  *outside* an active call has no live channel to consume it. PROT-10 stays covered by discovery refresh +
  management-API-driven invalidation (BND-7); full upstream-push coverage arrives when connection pooling lands and
  supersedes ADR-0012.

