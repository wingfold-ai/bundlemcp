"""The gateway's metrics in the Prometheus text format, one private registry per app."""

import time
from collections.abc import Awaitable, Callable

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from bundlemcp.application.contracts.observability.gateway_metrics import (
    RateLimitScope,
    ToolCallStatus,
)
from bundlemcp.application.contracts.observability.metrics_exposition import MetricsPage

# seconds, from a quick cache read to a long upstream call
DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60)
# a store is checked at most this often, however often the replica is scraped
STORE_HEALTH_TTL_SECONDS = 5.0
STORES = ("postgres", "valkey")

StoreHealthCheck = Callable[[], Awaitable[dict[str, bool]]]


class PrometheusMetrics:
    """``GatewayMetrics`` and ``MetricsExposition`` over ``prometheus_client``.

    The registry is this instance's own, never the library's global one, so
    two apps in one process (tests, or an embedding application) never share
    a counter. Gauges whose value lives elsewhere are read at scrape time:
    the open streams and the audit queue from callbacks, store health from a
    check cached for five seconds.
    """

    def __init__(
        self,
        *,
        open_streams: Callable[[], int] = lambda: 0,
        audit_queue_depth: Callable[[], int] = lambda: 0,
        store_health: StoreHealthCheck | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.registry = CollectorRegistry()
        self._calls = Counter(
            "bundlemcp_tool_calls",
            "Tool calls, by how they ended",
            ["endpoint", "server", "status"],
            registry=self.registry,
        )
        self._durations = Histogram(
            "bundlemcp_tool_call_duration_seconds",
            "Time from admitting a tool call to its answer",
            ["endpoint", "server", "status"],
            buckets=DURATION_BUCKETS,
            registry=self.registry,
        )
        self._rejected = Counter(
            "bundlemcp_rate_limit_rejections",
            "Requests refused by a rate limit",
            ["endpoint", "limit"],
            registry=self.registry,
        )
        self._traffic_open = Counter(
            "bundlemcp_traffic_limiter_fail_open",
            "Requests the traffic limiter let through because its store was unreachable",
            registry=self.registry,
        )
        self._auth_open = Counter(
            "bundlemcp_auth_limiter_fail_open",
            "Checks the auth-failure limiter skipped because its store was unreachable",
            registry=self.registry,
        )
        self._auth_failed = Counter(
            "bundlemcp_auth_failures",
            "Requests whose credential was refused",
            registry=self.registry,
        )
        self._locked_out = Counter(
            "bundlemcp_auth_lockouts",
            "Times a client was locked out after repeated failures",
            registry=self.registry,
        )
        self._denied = Counter(
            "bundlemcp_metering_denies",
            "Tool calls the metering hook denied",
            ["endpoint"],
            registry=self.registry,
        )
        self._in_flight = Gauge(
            "bundlemcp_upstream_in_flight_calls",
            "Upstream tool calls running now",
            ["server"],
            registry=self.registry,
        )
        self._upstream_failed = Counter(
            "bundlemcp_upstream_call_failures",
            "Upstream tool calls that did not get an answer",
            ["server"],
            registry=self.registry,
        )
        self._degraded = Counter(
            "bundlemcp_tools_list_degraded",
            "tools/list answers that listed the cached tools of an unhealthy member",
            ["endpoint", "server"],
            registry=self.registry,
        )
        Gauge(
            "bundlemcp_open_streams",
            "Notification streams this replica holds",
            registry=self.registry,
        ).set_function(lambda: float(open_streams()))
        Gauge(
            "bundlemcp_audit_queue_depth",
            "Audit records waiting to be written",
            registry=self.registry,
        ).set_function(lambda: float(audit_queue_depth()))
        self._store_up = Gauge(
            "bundlemcp_store_up",
            "Whether the store answered its last check (1) or not (0)",
            ["store"],
            registry=self.registry,
        )
        self._store_health = store_health
        self._clock = clock
        self._checked_at: float | None = None

    # --- GatewayMetrics -------------------------------------------------------------------

    def tool_call_finished(
        self, *, endpoint: str, server: str, status: ToolCallStatus, seconds: float
    ) -> None:
        self._calls.labels(endpoint, server, status.value).inc()
        self._durations.labels(endpoint, server, status.value).observe(seconds)

    def rate_limit_rejected(self, *, endpoint: str, limit: RateLimitScope) -> None:
        self._rejected.labels(endpoint, limit.value).inc()

    def traffic_limiter_failed_open(self) -> None:
        self._traffic_open.inc()

    def auth_limiter_failed_open(self) -> None:
        self._auth_open.inc()

    def auth_failed(self) -> None:
        self._auth_failed.inc()

    def auth_locked_out(self) -> None:
        self._locked_out.inc()

    def metering_denied(self, *, endpoint: str) -> None:
        self._denied.labels(endpoint).inc()

    def upstream_call_started(self, *, server: str) -> None:
        self._in_flight.labels(server).inc()

    def upstream_call_finished(self, *, server: str, ok: bool) -> None:
        self._in_flight.labels(server).dec()
        if not ok:
            self._upstream_failed.labels(server).inc()

    def tools_list_degraded(self, *, endpoint: str, server: str) -> None:
        self._degraded.labels(endpoint, server).inc()

    # --- MetricsExposition ----------------------------------------------------------------

    async def render(self) -> MetricsPage:
        await self._refresh_store_health()
        return MetricsPage(content=generate_latest(self.registry), media_type=CONTENT_TYPE_LATEST)

    async def _refresh_store_health(self) -> None:
        if self._store_health is None:
            return
        now = self._clock()
        if self._checked_at is not None and now - self._checked_at < STORE_HEALTH_TTL_SECONDS:
            return
        self._checked_at = now
        try:
            health = await self._store_health()
        except Exception:
            health = {}
        for store in STORES:
            self._store_up.labels(store).set(1 if health.get(store) else 0)
