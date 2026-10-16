# ADR-0052: Each replica exports Prometheus metrics, behind management credentials, with a closed label set

**Status:** accepted · **Date:** 2026-10-16

## Context

The gateway counted rate-limit rejections, fail-opens, auth failures and lockouts into an untyped in-process sink
(`Counters.inc(name)`) that nothing exported, so operators could alert only on log lines. The traffic limiter and the
auth-failure limiter raised the same fail-open counter and could not be told apart, and nothing measured tool calls,
upstream failures, degraded listings or store health.

## Decision drivers

- What an operator alerts on is a metric, not a log line.
- A label value can never be a secret or a caller's identity, by construction rather than by review.
- Replicas scale by container, and no state a request depends on is per replica: counts must sum across replicas
  without the gateway aggregating anything.
- No second port, no second listener.

## Decision

- **A typed `GatewayMetrics` contract, one method per fact.** Labels are admin-chosen names (endpoint, server) or come
  from closed enums (call status, limit scope); no method takes a caller, a key, a header or an argument. It replaces
  `Counters`, which is deleted. The two limiters report fail-open separately.
- **A Prometheus adapter on a private registry**, never the library's global one, so two apps in one process never
  share a counter. Gauges whose value lives elsewhere (open streams, audit queue depth, store health) are read at
  scrape time; store health is checked at most every five seconds, each store within a short timeout.
- **`/metrics` on the main port, behind the management API's credentials** (a service key or an admin session): a
  `MetricsController` deriving from `ManagementController`, out of the OpenAPI document, mounted unless
  `BUNDLEMCP_METRICS_ENABLED=false`.
- **Each replica exports its own values**; Prometheus scrapes every replica and sums.
- **A degraded `tools/list`** (one that lists an unhealthy member's cached tools) is counted per endpoint and server and
  logged at WARN in the `tools/list` handler.

## Alternatives considered

- **Keep `Counters.inc(name)` and add a labels dict.** An untyped dict is exactly how a header value becomes a label.
- **An unauthenticated metrics port.** A second listener and a network-only boundary every deployment must get right;
  metrics name endpoints and servers and show traffic volume.
- **OpenTelemetry metrics with a Prometheus exporter.** Heavier, and the scrape format is the requirement; a bridge can
  be added later behind the same contract.
- **Export the global session count from Valkey.** Every replica would export the same number, and counting needs a
  scan.

## Consequences

### Positive

- Fail-open limiters, lockout storms, degraded listings and a store outage are visible on a dashboard.
- A new counted fact is one method on the contract and one metric in the adapter.

### Trade-offs

- A scrape resolves the service key once, as any management call does.
- Counters reset when a replica restarts; `rate()` and `increase()` handle that.
- Label cardinality grows with endpoints × servers, bounded by configuration; there are no per-tool or per-caller
  labels.
