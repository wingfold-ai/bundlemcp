# ADR-0008: Full bidirectional MCP proxy fidelity

**Status:** accepted · **Date:** 2026-07-02

## Context

A tools-only gateway breaks real workloads: long-running calls (a video render takes ~130 s) need progress +
progress-aware timeouts + cancellation; modern upstreams initiate sampling/elicitation requests toward the client. The
cheaper alternative (relay progress/cancellation, reject sampling/ elicitation) was considered and declined in the
2026-07 scope review.

## Decision drivers

- Proxy transparency: upstreams behind bundlemcp should not lose protocol features they'd have when connected directly.
- Elicitation is also the natural UX for per-user upstream OAuth connects (UPS-27).
- Doing it now shapes the session model correctly; bolting it on later would rework spec/30.

## Decision

bundlemcp relays the **full protocol surface** bidirectionally, across replicas
([spec/32](../../openspec/specs/protocol/spec.md)): progress, cancellation, logging, ping, completions,
list-changed, and server→client requests (sampling/createMessage, elicitation/create, roots/list), with capability
gating (PROT-5). The endpoint GET event stream is mandatory (EP-1a); cross-replica delivery rides Redis pub/sub
(SES-13).

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- No silent protocol degradation; future MCP features have a relay home.

### Trade-offs

- The hardest engineering in the project: replica-pinned streams + pub/sub routing + request/response correlation.
  Explicitly budgeted as the first implementation spike.
- More surface to test (SES-12 style integration tests extend to bidirectional flows).

