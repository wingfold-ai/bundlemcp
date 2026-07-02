# 51 — Observability

**Status:** Accepted · **Origin:** new

## Summary

Structured logs, Prometheus metrics, and health probes as first-class
requirements — metamcp's silent partial failures and debug-noise-in-hot-paths
taught that observability can't be an afterthought.

## Requirements

- **OBS-1 Logs**: structured JSON to stdout (structlog or equivalent);
  level via `BUNDLEMCP_LOG_LEVEL`. Every request log line carries request id,
  endpoint, session id, caller where resolved. Secrets, tokens, header
  values, and tool arguments MUST never be logged. No debug prints in hot
  paths — enforced by ruff config (`T20`) and review.
- **OBS-2 Metrics**: Prometheus `/metrics` (gateway-internal port or
  behind service auth) exposing at minimum: tool call count + duration
  histogram (labels: endpoint, server, status), active session gauge,
  upstream connection gauge + failure counter (per server), rate-limit
  rejections, metering denies, audit queue depth, Redis/Postgres health.
- **OBS-3 Probes**: `/healthz` (process live) and `/readyz` (Postgres +
  Redis reachable, migrations applied) — unauthenticated, for
  orchestrators.
- **OBS-4 Degraded-response visibility**: when an endpoint serves a partial
  `tools/list` because an upstream failed ([DISC-4](11-tool-discovery.md)),
  that MUST increment a dedicated metric and produce a WARN log — the
  metamcp "tripwire" promoted to a requirement.
- **OBS-5 Tracing (optional)**: OpenTelemetry instrumentation
  (FastAPI/SQLAlchemy/redis auto-instrumentation + a span per upstream tool
  call), enabled via standard `OTEL_*` env vars; off by default and zero-cost
  when disabled.
- **OBS-6 Overhead budget**: the gateway's added latency on a `tools/call`
  (client→gateway→upstream vs. direct upstream call) SHOULD stay under
  **50 ms p95** in the integration environment; the integration suite
  measures and reports it so regressions are visible (a report, not a hard
  gate, in v1).

## Out of scope

- Bundled Grafana dashboards / alert rules (nice-to-have docs example, not a
  requirement).

## Open questions

- None.
