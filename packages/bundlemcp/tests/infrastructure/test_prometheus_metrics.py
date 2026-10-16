"""The metrics each recorded fact produces, by name and labels (OPS-9, EP-21)."""

import pytest
from bundlemcp.application.contracts.observability.gateway_metrics import (
    RateLimitScope,
    ToolCallStatus,
)
from bundlemcp.infrastructure.prometheus.prometheus_metrics import PrometheusMetrics


def _value(metrics: PrometheusMetrics, name: str, **labels: str) -> float | None:
    return metrics.registry.get_sample_value(name, labels or None)


def test_ops9_a_tool_call_is_counted_and_timed():
    metrics = PrometheusMetrics()
    labels = {"endpoint": "main", "server": "echo", "status": "success"}
    metrics.tool_call_finished(
        endpoint="main", server="echo", status=ToolCallStatus.SUCCESS, seconds=0.02
    )
    assert _value(metrics, "bundlemcp_tool_calls_total", **labels) == 1
    assert _value(metrics, "bundlemcp_tool_call_duration_seconds_count", **labels) == 1
    assert _value(metrics, "bundlemcp_tool_call_duration_seconds_bucket", **labels, le="0.025") == 1


def test_ops9_each_fact_has_its_metric():
    metrics = PrometheusMetrics()
    metrics.rate_limit_rejected(endpoint="main", limit=RateLimitScope.CLIENT)
    metrics.metering_denied(endpoint="main")
    metrics.auth_failed()
    metrics.auth_locked_out()
    metrics.upstream_call_started(server="echo")
    assert _value(metrics, "bundlemcp_upstream_in_flight_calls", server="echo") == 1
    metrics.upstream_call_finished(server="echo", ok=False)
    metrics.tools_list_degraded(endpoint="main", server="weather")
    assert _value(metrics, "bundlemcp_rate_limit_rejections_total", endpoint="main", limit="client")
    assert _value(metrics, "bundlemcp_metering_denies_total", endpoint="main") == 1
    assert _value(metrics, "bundlemcp_auth_failures_total") == 1
    assert _value(metrics, "bundlemcp_auth_lockouts_total") == 1
    assert _value(metrics, "bundlemcp_upstream_in_flight_calls", server="echo") == 0
    assert _value(metrics, "bundlemcp_upstream_call_failures_total", server="echo") == 1
    assert _value(
        metrics, "bundlemcp_tools_list_degraded_total", endpoint="main", server="weather"
    ) == 1


def test_ep21_the_two_limiters_fail_open_on_separate_alarms():
    """EP-21: the auth-failure limiter's fail-open is told apart from the traffic limiter's."""
    metrics = PrometheusMetrics()
    metrics.auth_limiter_failed_open()
    assert _value(metrics, "bundlemcp_auth_limiter_fail_open_total") == 1
    assert _value(metrics, "bundlemcp_traffic_limiter_fail_open_total") == 0


def test_ops9_gauges_are_read_at_scrape_time():
    streams = [3]
    metrics = PrometheusMetrics(open_streams=lambda: streams[0], audit_queue_depth=lambda: 7)
    assert _value(metrics, "bundlemcp_open_streams") == 3
    streams[0] = 5
    assert _value(metrics, "bundlemcp_open_streams") == 5
    assert _value(metrics, "bundlemcp_audit_queue_depth") == 7


async def test_ops9_store_health_gauge_is_cached_for_five_seconds():
    """OPS-9: store health is checked at scrape time, at most every five seconds."""
    calls = []
    now = [100.0]

    async def health():
        calls.append(now[0])
        return {"postgres": True, "valkey": len(calls) > 1}

    metrics = PrometheusMetrics(store_health=health, clock=lambda: now[0])
    page = await metrics.render()
    assert b'bundlemcp_store_up{store="valkey"} 0.0' in page.content
    assert b'bundlemcp_store_up{store="postgres"} 1.0' in page.content
    await metrics.render()
    assert len(calls) == 1
    now[0] += 6
    page = await metrics.render()
    assert b'bundlemcp_store_up{store="valkey"} 1.0' in page.content


async def test_ops9_a_failing_store_check_reads_as_down():
    async def broken():
        raise RuntimeError("no answer")

    page = await PrometheusMetrics(store_health=broken).render()
    assert b'bundlemcp_store_up{store="postgres"} 0.0' in page.content


def test_ops9_two_instances_never_share_a_counter():
    first, second = PrometheusMetrics(), PrometheusMetrics()
    first.auth_failed()
    assert _value(first, "bundlemcp_auth_failures_total") == 1
    assert _value(second, "bundlemcp_auth_failures_total") == 0


@pytest.mark.parametrize("status", list(ToolCallStatus))
def test_ops9_statuses_are_a_closed_set(status):
    assert status.value in {"success", "error", "denied"}
