# Proposal: add Prometheus metrics

## Why

The gateway collects four in-process counters (rate-limit rejections, rate-limit fail-open, auth failures, auth
lockouts) and an audit drop count, but nothing exports them: there is no `/metrics` route and no Prometheus dependency.
Two docstrings (`infrastructure/inprocess/counters.py`, `infrastructure/postgres/audit_writer.py`) even claim an export
that does not exist. Operators can only alert on log lines, so a fail-open limiter, a lockout storm or a degraded
`tools/list` is invisible to a dashboard — the "never silently" promises of EP-21 and UPS-20 hold only for whoever
reads the logs.

## What Changes

- A Prometheus text-format `/metrics` route on the gateway (OPS-9), authenticated like the management API (service key
  or admin session), exporting: tool-call count and duration histogram (endpoint, server, status), active sessions,
  upstream in-flight calls and failures per server, rate-limit rejections, metering denies, auth failures and lockouts,
  audit queue depth, and store health.
- A dedicated degraded-`tools/list` metric plus a WARN log whenever an endpoint lists tools while a member upstream is
  unhealthy (OPS-11).
- Rate-limit rejections and the traffic limiter's fail-open counted in the exported metrics (EP-18); the auth-failure
  limiter's fail-open raises its **own** alarm metric, distinct from the traffic limiter's (EP-21).
- Lockout events visible in metrics (SEC-9).
- Metric labels never carry secrets or caller identity; a unit-test redaction helper asserts it on representative
  paths (SEC-10).
- `/metrics` added to what the gateway container serves (ARC-11).
- The two false docstrings are corrected as part of the implementation (the docs-only correction until then is in
  [fix-stale-documentation](../fix-stale-documentation/proposal.md)).

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `operations`: ADDED OPS-9 (Prometheus metrics) and OPS-11 (degraded-response visibility).
- `architecture`: MODIFIED ARC-11 (`/metrics` is one of the gateway's routes).
- `endpoints`: MODIFIED EP-18 (rejections in exported metrics) and EP-21 (dedicated auth-limiter fail-open alarm).
- `security`: MODIFIED SEC-9 (lockouts visible in metrics) and SEC-10 (no secrets in metric labels; redaction helper).

## Impact

- **Code:** a metrics contract in `application/contracts/`, a Prometheus adapter in `infrastructure/`, a
  `MetricsController` in `api/`, wiring in `main/`; the rate limiter, auth-failure limiter, tool-call pipeline, audit
  writer and `tools/list` handler record into the contract instead of the untyped `Counters` sink.
- **Dependencies:** `prometheus-client` (Apache-2.0) added to `packages/bundlemcp`.
- **Settings:** new `BUNDLEMCP_METRICS_ENABLED` (default on).
- **Docs:** `docs/self-hosting/operations.md`, `requirements.md` and `configuration.md` stop saying there is no
  `/metrics`; a scrape-config example. An ADR records the export model (per-replica scrape, service-key auth, closed
  label set) — next free number in `docs/adr/`.
- **Dependents:** [harden-audit-log](../harden-audit-log/proposal.md) counts audit overflow and failed writes through
  this change's metrics; [improve-request-observability](../improve-request-observability/proposal.md) is independent.
- No API DTO changes; `/metrics` is excluded from the OpenAPI document.
