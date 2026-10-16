"""Optional OpenTelemetry tracing: off and free by default, no secrets when on (OPS-12)."""

import builtins
import subprocess
import sys

import pytest
from bundlemcp.main.tracing_switch import start_tracing, tracing_requested
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from structlog.testing import capture_logs

from tests.api.test_gateway import _initialize, _rpc, _running
from tests.conftest import ENDPOINT_KEY

SECRET_ARGUMENT = "argument-that-must-not-be-traced"
SECRET_HEADER = "tenant-value-that-must-not-be-traced"


def test_ops12_tracing_is_requested_only_by_an_exporter_endpoint():
    assert not tracing_requested({})
    assert tracing_requested({"OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318"})
    assert tracing_requested({"OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://c/v1/traces"})
    assert not tracing_requested(
        {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318", "OTEL_SDK_DISABLED": "true"}
    )


def test_ops12_off_loads_no_tracing_code():
    """OPS-12: with no exporter configured, building the app loads none of the gateway's
    tracing code, no instrumentation and no exporter. (The MCP library imports the
    OpenTelemetry API itself, and redis-py the SDK's metrics when the SDK is installed.)"""
    script = (
        "import sys\n"
        "from bundlemcp.infrastructure.config.settings import EnvSettings\n"
        "from bundlemcp.main.app import create_app\n"
        "create_app(EnvSettings(_env_file=None, database_url='sqlite+aiosqlite://'))\n"
        "tracing = ('bundlemcp.infrastructure.opentelemetry', 'opentelemetry.instrumentation',"
        " 'opentelemetry.exporter', 'opentelemetry.sdk.trace')\n"
        "loaded = [m for m in sys.modules if m.startswith(tracing)]\n"
        "print(loaded)\n"
    )
    env = {k: v for k, v in __import__("os").environ.items() if not k.startswith("OTEL_")}
    done = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=120
    )
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip().splitlines()[-1] == "[]"


@pytest.fixture
def traced(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.invalid:4318")
    exporter = InMemorySpanExporter()
    return exporter, SimpleSpanProcessor(exporter)


async def test_ops12_upstream_call_span_attributes(engine, redis, traced):
    """OPS-12: a traced call has a span for the upstream call, a child of the request's span,
    naming the endpoint, server, tool and status."""
    exporter, processor = traced
    async with _running(engine, redis, span_processor=processor) as (http, _app):
        session = await _initialize(http)
        call = {"name": "echo__say", "arguments": {"text": "x"}}
        resp = await _rpc(http, "main", session, "tools/call", call)
        assert resp.json()["result"]["content"][0]["text"] == "echo:x"
    spans = exporter.get_finished_spans()
    [upstream] = [span for span in spans if span.name == "mcp.upstream_call"]
    assert dict(upstream.attributes) == {
        "bundlemcp.endpoint": "main",
        "bundlemcp.server": "echo",
        "bundlemcp.tool": "say",
        "bundlemcp.status": "success",
    }
    parents = {span.context.span_id: span for span in spans}
    assert upstream.parent is not None and upstream.parent.span_id in parents
    assert parents[upstream.parent.span_id].kind.name == "SERVER"


async def test_ops12_spans_carry_no_secrets(engine, redis, traced):
    """OPS-12: no exported span holds the API key, a forwarded header value or the arguments."""
    exporter, processor = traced
    async with _running(engine, redis, span_processor=processor) as (http, _app):
        session = await _initialize(http)
        call = {"name": "notes__write_note", "arguments": {"text": SECRET_ARGUMENT}}
        await http.post(
            "/main/mcp",
            headers={"Mcp-Session-Id": session, "x-tenant": SECRET_HEADER},
            json={"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": call},
        )
    values = [
        str(value)
        for span in exporter.get_finished_spans()
        for value in (span.attributes or {}).values()
    ]
    assert values
    for secret in (ENDPOINT_KEY, SECRET_ARGUMENT, SECRET_HEADER):
        assert not any(secret in value for value in values), secret


def test_ops12_missing_extra_warns_once(monkeypatch):
    """OPS-12: configured but not installed, the gateway starts untraced with one warning."""
    real_import = builtins.__import__

    def without_tracing(name, *args, **kwargs):
        if name == "bundlemcp.infrastructure.opentelemetry.tracing":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_tracing)
    with capture_logs() as logs:
        assert start_tracing(object()) is None
    assert [(entry["event"], entry["log_level"]) for entry in logs] == [
        ("tracing.extra_missing", "warning")
    ]
