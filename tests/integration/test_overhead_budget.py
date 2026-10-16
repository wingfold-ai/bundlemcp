"""The latency the gateway adds to a tools/call, reported against a budget (OPS-13).

A report, not a gate: the test fails only if a call fails. The figures go to
stdout and to a JSON file (``BUNDLEMCP_OVERHEAD_REPORT``, default
``overhead-report.json``) that CI uploads and adds to the job summary.
"""

import asyncio
import json
import os
import statistics
import sys
import time

import pytest
from conftest import GATEWAY_URL, SERVICE_KEY  # noqa: TID252
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from helpers import wait_ready

ECHO_URL = os.environ.get("BUNDLEMCP_ECHO_URL", "http://127.0.0.1:9100/mcp")
REPORT = os.environ.get("BUNDLEMCP_OVERHEAD_REPORT", "overhead-report.json")
BUDGET_MS = 50.0
WARMUP = 20
SAMPLES = 200

pytestmark = pytest.mark.benchmark


async def _latencies(url: str, tool: str, headers: dict[str, str]) -> list[float]:
    """Milliseconds per call over one open session, after a warm-up."""
    async with Client(StreamableHttpTransport(url, headers=headers)) as client:
        for _ in range(WARMUP):
            await client.call_tool(tool, {"text": "warm"})
        samples = []
        for turn in range(SAMPLES):
            started = time.perf_counter()
            result = await client.call_tool(tool, {"text": f"x{turn}"})
            samples.append((time.perf_counter() - started) * 1000)
            assert not result.is_error
    return samples


def _percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))]


def test_ops13_overhead_is_reported():
    """OPS-13: direct and gateway p50/p95, the p95 overhead and the 50 ms budget, reported."""
    wait_ready(GATEWAY_URL)
    direct = asyncio.run(_latencies(ECHO_URL, "echo", {}))
    gateway = asyncio.run(
        _latencies(
            f"{GATEWAY_URL}/demo/mcp", "echo__echo", {"Authorization": f"Bearer {SERVICE_KEY}"}
        )
    )
    report = {
        "samples": SAMPLES,
        "direct_ms": {"p50": statistics.median(direct), "p95": _percentile(direct, 0.95)},
        "gateway_ms": {"p50": statistics.median(gateway), "p95": _percentile(gateway, 0.95)},
        "budget_ms": BUDGET_MS,
    }
    report["overhead_p95_ms"] = report["gateway_ms"]["p95"] - report["direct_ms"]["p95"]
    report["within_budget"] = report["overhead_p95_ms"] <= BUDGET_MS
    with open(REPORT, "w") as out:
        json.dump(report, out, indent=2)
    sys.stdout.write(
        "\n| path | p50 ms | p95 ms |\n|---|---|---|\n"
        f"| direct | {report['direct_ms']['p50']:.1f} | {report['direct_ms']['p95']:.1f} |\n"
        f"| gateway | {report['gateway_ms']['p50']:.1f} | {report['gateway_ms']['p95']:.1f} |\n"
        f"\np95 overhead {report['overhead_p95_ms']:.1f} ms against a {BUDGET_MS:.0f} ms budget: "
        f"{'within' if report['within_budget'] else 'EXCEEDED'}\n"
    )
