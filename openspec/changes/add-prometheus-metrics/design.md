# Design: add Prometheus metrics

## Context

See [proposal.md](proposal.md) for the motivation. Today:

- `application/contracts/live_state/counters.py` defines an untyped `Counters` protocol (`inc(name)`, `get`,
  `snapshot`) and four name constants. `infrastructure/inprocess/counters.py::InProcessCounters` is its only
  implementation, built in `CompositionRoot._compose()` and handed to the rate-limit gate, `ValkeyRateLimiter` and
  `ValkeyAuthFailureLimiter`. Nothing reads `snapshot()` outside tests.
- `ValkeyAuthFailureLimiter` wraps a `ValkeyRateLimiter` sharing the same sink, so its fail-open increments the same
  `rate_limit_fail_open` name as the traffic limiter — the two cannot be told apart (the EP-21 gap).
- `QueuedAuditWriter.dropped` is a plain attribute; queue depth is not observable.
- `tools/list` never contacts an upstream (UPS-20, ADR-0038); it serves the Postgres cache. "Degraded" therefore means
  "the listing includes a member whose `health_status` is `error`", which `BundleView` already knows per member.
- The gateway runs one uvicorn process per container (`apps/gateway/main.py`); replicas scale by container.

## Goals / Non-Goals

**Goals:**

- One typed metrics contract the application and API layers record into; label values come only from closed sets.
- Per-replica export that sums correctly across replicas.
- The metric set of OPS-9, plus the EP-21 alarm split and the OPS-11 degraded counter.

**Non-Goals:**

- Grafana dashboards or alert rules (observability out of scope); a docs example of a scrape config and a few PromQL
  alerts is enough.
- Cross-replica aggregation inside the gateway (Prometheus does it).
- OpenTelemetry metrics — tracing is OPS-12 in
  [improve-request-observability](../archive/2026-10-16-improve-request-observability/proposal.md); metrics stay
  Prometheus-native.
- Per-tool or per-caller labels.

## Decisions

### D1. A typed `GatewayMetrics` contract replaces the untyped `Counters` sink

`application/contracts/observability/gateway_metrics.py` declares a `@runtime_checkable` `Protocol` with one method per
fact: `tool_call_finished(endpoint, server, status, seconds)`, `rate_limit_rejected(endpoint, limit)`,
`traffic_limiter_failed_open()`, `auth_limiter_failed_open()`, `auth_failed()`, `auth_locked_out()`,
`metering_denied(endpoint)`, `upstream_call_started/finished(server, ok)`, `tools_list_degraded(endpoint, server)`,
plus gauge sources registered at composition (D4). `status` and `limit` are enums, not strings.

- *Why:* a method per fact makes the closed label set a type, which is what keeps secrets and caller identity out of
  labels (SEC-10) — there is no parameter to put a `sub` in. It also lets the redaction test enumerate every call site.
- *Alternative:* keep `Counters.inc(name)` and add `labels: dict[str, str]`. Rejected: an untyped dict is the shape
  that lets a header value become a label, and CLAUDE.md forbids untyped dicts across layers.
- `Counters`, its constants and `InProcessCounters` are deleted once every caller moved (no shim kept).

### D2. `prometheus-client` in an infrastructure adapter with its own registry

`infrastructure/prometheus/prometheus_metrics.py` implements the contract over a private `CollectorRegistry` (never the
library's global default), so tests build isolated instances and two apps in one test process do not collide. A memory
fake `infrastructure/memory/recording_metrics.py` records calls for application-layer tests.

- *Alternative:* OpenTelemetry metrics SDK with a Prometheus exporter. Rejected for now: heavier, and the scrape format
  is the requirement. OPS-12 can add an OTLP bridge later without changing the contract.

### D3. `/metrics` on the main port, behind the management auth

`api/metrics/controllers/metrics_controller.py` — a `MetricsController` whose router-level dependency is the same
`ManagementAuth` (`api/http/management_auth.py`) that `ManagementController` declares, so the policy is the management
API's (service key or admin session; endpoint keys get 403). `include_in_schema = False`;
mounted at root in `main/app.py`. It returns the adapter's exposition text with the Prometheus content type. With
`BUNDLEMCP_METRICS_ENABLED=false` the controller is not mounted (404).

- *Why:* Prometheus supports bearer authorization in a scrape config; one port keeps the container, compose file and
  health check unchanged. Metrics reveal endpoint and server names and traffic volume, so they are not public.
- *Alternative:* a second, unauthenticated internal port (`BUNDLEMCP_METRICS_PORT`). Rejected: a second listener in
  the same process, a second port in every deployment, and a network-only boundary the operator must get right. It can
  be added later as an opt-in without changing OPS-9.
- *Note on the management API's auth cost:* a scrape every 15 s resolves the service key once per scrape; that is the
  same lookup every management call does.

### D4. Gauges are read at scrape time from replica-local sources

- **Active sessions:** a gauge callback over the replica's `StreamRegistry` (open session streams and in-flight calls
  held by this replica). The global count of session records in Valkey is not exported: every replica would export the
  same number (double counting) and counting needs a `SCAN`.
- **Audit queue depth:** a callback over the audit writer's queue size.
- **Upstream in-flight calls:** a gauge incremented/decremented around the upstream call in the tool-call pipeline, per
  server. With per-call clients (ADR-0012) this is what "upstream connection gauge" means today; when pooling lands
  ([add-upstream-session-pooling](../add-upstream-session-pooling/proposal.md)) the pool reports its open connections
  into the same gauge.
- **Store health:** a gauge per store (`postgres`, `valkey`) set by running the existing `ReadinessProbe` checks
  separately at scrape time with a short timeout, cached for 5 s so frequent scrapes do not add load.

### D5. Metric names and labels

Prefix `bundlemcp_`. Counters end `_total`; the duration histogram is in seconds with buckets from 5 ms to 60 s.
Labels: `endpoint` and `server` (admin-chosen names, bounded by configuration), `status` (`success|error|denied`),
`limit` (`endpoint|client`), `store`. A call denied before routing has `server=""`. No label ever holds a caller id,
`sub`, API key id, tool argument, header value or client IP.

### D6. OPS-11 is decided in the `tools/list` handler

`ToolsListHandler` asks the view which members are in `HealthStatus.ERROR`; for each it calls
`metrics.tools_list_degraded(endpoint, server)` and logs `tools_list.degraded` at WARN with endpoint and server. The
listing itself is unchanged (UPS-20).

### D7. Which layer each piece lives in

| Piece | Layer |
|---|---|
| `GatewayMetrics` protocol, `ToolCallStatus`/`RateLimitScope` enums | `application/contracts/observability/` |
| Prometheus adapter, memory fake | `infrastructure/prometheus/`, `infrastructure/memory/` |
| `MetricsController` | `api/metrics/controllers/` |
| Wiring, gauge callbacks, `BUNDLEMCP_METRICS_ENABLED` | `main/`, `application/settings/` |
| Redaction test helper | `packages/bundlemcp/tests/redaction.py` (test code only) |

`api/` names only the contract; `lint-imports` enforces it.

## Risks / Trade-offs

- [Label cardinality grows with endpoints × servers] → bounded by admin configuration; documented, and no per-tool or
  per-caller labels.
- [A slow store makes scrapes slow] → per-store timeout and a 5 s cache on the health gauge.
- [Counters reset on restart] → normal Prometheus semantics; `rate()`/`increase()` handle resets.
- [Two changes touch the audit writer] → this change only exposes its depth and drop count; durability is
  [harden-audit-log](../harden-audit-log/proposal.md).

## Migration Plan

Additive. Deploy, add a scrape job with a service key to Prometheus per replica (docs example). Rollback: set
`BUNDLEMCP_METRICS_ENABLED=false` or deploy the previous image; no schema change.
