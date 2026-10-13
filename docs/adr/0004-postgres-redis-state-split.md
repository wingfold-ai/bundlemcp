# ADR-0004: Postgres = durable state, Redis = live state; no in-memory-only state

**Status:** accepted · **Date:** 2026-07-02

## Context

metamcp's #1 production failure: sessions, pools, and counters lived in process memory — restarts dropped everything,
replicas were impossible. The rewrite's headline quality goals are "restarts are non-events" and "any replica serves any
session".

## Decision drivers

- Directly eliminates the failure mode that motivated the rewrite.
- Redis was accepted as an additional required service precisely because Postgres-only session storage would put
  hot-path session churn on the system of record.

## Decision

Two-store split (ARC-7/8/9/10 in [spec/01](../../openspec/specs/architecture/spec.md)): Postgres holds everything
durable (config, users, tokens, audit); Redis holds everything live (sessions, bindings, rate limits, log ring,
pub/sub). **No request may depend on process-local state.** A session is data, not an object
([spec/30](../../openspec/specs/sessions/spec.md)); cross-replica signaling and config invalidation ride Redis
pub/sub
([spec/32](../../openspec/specs/protocol/spec.md),
[spec/33](../../openspec/specs/sessions/spec.md)).

## Alternatives considered

_Not recorded at the time of the decision._

## Consequences

### Positive

- Rolling restarts and horizontal scaling without sticky sessions.

### Trade-offs

- Redis becomes availability-critical for live traffic; behavior under outage is explicitly specified (degradation
  matrix SES-14, EP-21) instead of hand-waved.
- Live streams remain replica-pinned; cross-replica delivery machinery (SES-13) is the price of the model.

