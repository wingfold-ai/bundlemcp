"""The /metrics route and what it counts (OPS-9, OPS-11, EP-18, EP-21, SEC-9, SEC-10)."""

import json

from bundlemcp.domain.servers.health_status import HealthStatus
from bundlemcp.infrastructure.config.settings import EnvSettings
from bundlemcp.infrastructure.memory.recording_metrics import RecordingMetrics
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.valkey.auth_failure_limiter import ValkeyAuthFailureLimiter
from bundlemcp.main.app import create_app
from bundlemcp.main.composition_overrides import CompositionOverrides
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from structlog.testing import capture_logs

from tests.api.test_gateway import RecordingHook, _initialize, _rpc, _running, upstream_factory
from tests.conftest import ENDPOINT_KEY, SERVICE_KEY, hermetic_settings, seed_api_key
from tests.redaction import assert_redacted

SAY = {"name": "echo__say", "arguments": {"text": "x"}}
SERVICE = {"Authorization": f"Bearer {SERVICE_KEY}"}


def _sample(text: str, name: str, **labels: str) -> float:
    """The value of one sample in exposition text, 0 when absent."""
    wanted = ",".join(f'{key}="{value}"' for key, value in sorted(labels.items()))
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        metric, _, value = line.rpartition(" ")
        if "{" in metric:
            base, _, rest = metric.partition("{")
            got = ",".join(sorted(rest.rstrip("}").split(",")))
        else:
            base, got = metric, ""
        if base == name and got == wanted:
            return float(value)
    return 0.0


async def _scrape(http) -> str:
    resp = await http.get("/metrics", headers=SERVICE)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/plain")
    return resp.text


async def test_ops9_metrics_requires_service_key(engine, redis):
    """OPS-9: no credential is 401, an endpoint key 403, a service key 200; none leak values."""
    await seed_api_key(engine, SERVICE_KEY)
    async with _running(engine, redis) as (http, _app):
        anonymous = await http.get("/metrics", headers={"Authorization": ""})
        endpoint_key = await http.get(
            "/metrics", headers={"Authorization": f"Bearer {ENDPOINT_KEY}"}
        )
        service = await http.get("/metrics", headers=SERVICE)
    assert anonymous.status_code == 401 and "bundlemcp_" not in anonymous.text
    assert endpoint_key.status_code == 403 and "bundlemcp_" not in endpoint_key.text
    assert service.status_code == 200 and "bundlemcp_tool_calls" in service.text


async def test_ops9_metrics_disabled_is_404(engine, redis):
    await seed_api_key(engine, SERVICE_KEY)
    settings = hermetic_settings(metrics_enabled=False)
    async with _running(engine, redis, settings=settings) as (http, _app):
        assert (await http.get("/metrics", headers=SERVICE)).status_code == 404


async def test_ops9_tool_call_counted_and_timed(engine, redis):
    """OPS-9: a successful call adds one to the counter and one observation to the histogram."""
    await seed_api_key(engine, SERVICE_KEY)
    async with _running(engine, redis) as (http, _app):
        session = await _initialize(http)
        assert (await _rpc(http, "main", session, "tools/call", SAY)).status_code == 200
        text = await _scrape(http)
    labels = {"endpoint": "main", "server": "echo", "status": "success"}
    assert _sample(text, "bundlemcp_tool_calls_total", **labels) == 1
    assert _sample(text, "bundlemcp_tool_call_duration_seconds_count", **labels) == 1
    assert _sample(text, "bundlemcp_upstream_in_flight_calls", server="echo") == 0


async def test_ops9_metering_deny_counted(engine, redis):
    """OPS-9: a call the metering hook denies counts as a deny and a denied call."""
    await seed_api_key(engine, SERVICE_KEY)
    hook = RecordingHook()
    hook.deny_reason = "insufficient_credits"
    async with _running(engine, redis, metering_hook=hook) as (http, _app):
        session = await _initialize(http)
        await _rpc(http, "main", session, "tools/call", SAY)
        text = await _scrape(http)
    assert _sample(text, "bundlemcp_metering_denies_total", endpoint="main") == 1
    labels = {"endpoint": "main", "server": "echo", "status": "denied"}
    assert _sample(text, "bundlemcp_tool_calls_total", **labels) == 1


async def test_ops9_replicas_export_their_own_counters(engine, redis):
    """OPS-9: two apps on one database and one Valkey; a call served by A counts on A only."""
    await seed_api_key(engine, SERVICE_KEY)
    async with _running(engine, redis) as (a, _app_a):
        app_b = create_app(
            EnvSettings(_env_file=None, database_url="sqlite+aiosqlite://"),
            overrides=CompositionOverrides(
                engine=engine, redis=redis, client_factory=upstream_factory
            ),
        )
        transport = ASGITransport(app=app_b)
        async with AsyncClient(transport=transport, base_url="http://gw") as b:
            async with app_b.router.lifespan_context(app_b):
                session = await _initialize(a)
                await _rpc(a, "main", session, "tools/call", SAY)
                labels = {"endpoint": "main", "server": "echo", "status": "success"}
                assert _sample(await _scrape(a), "bundlemcp_tool_calls_total", **labels) == 1
                assert _sample(await _scrape(b), "bundlemcp_tool_calls_total", **labels) == 0


async def test_ops9_store_health_gauge(engine, redis, monkeypatch):
    """OPS-9: with Valkey unreachable the gauge reads 0 for valkey and 1 for postgres."""
    await seed_api_key(engine, SERVICE_KEY)

    async def refuse():
        raise ConnectionError("refused")

    async with _running(engine, redis) as (http, _app):
        monkeypatch.setattr(redis, "ping", refuse)
        text = await _scrape(http)
    assert _sample(text, "bundlemcp_store_up", store="valkey") == 0
    assert _sample(text, "bundlemcp_store_up", store="postgres") == 1


async def test_ep18_rejection_counted_in_metrics(engine, redis):
    """EP-18: a rate-limit rejection appears in the exported metrics."""
    from tests.api.test_gateway import _set_rate_limit

    await seed_api_key(engine, SERVICE_KEY)
    async with _running(engine, redis) as (http, app):
        await _set_rate_limit(app, {"endpoint": {"limit": 1, "window_seconds": 100}})
        session = await _initialize(http)
        await _rpc(http, "main", session, "tools/call", SAY)
        assert (await _rpc(http, "main", session, "tools/call", SAY)).status_code == 429
        text = await _scrape(http)
    assert _sample(text, "bundlemcp_rate_limit_rejections_total", endpoint="main", limit="endpoint")


async def test_ep21_auth_limiter_fail_open_has_own_alarm():
    """EP-21: the auth-failure limiter failing open raises its own alarm and a WARN."""

    class BoomRedis:
        async def time(self):
            raise ConnectionError("down")

        async def get(self, key):
            raise ConnectionError("down")

    metrics = RecordingMetrics()
    limiter = ValkeyAuthFailureLimiter(BoomRedis(), limit=1, window=100, metrics=metrics)
    with capture_logs() as logs:
        assert (await limiter.locked_out("1.2.3.4")).allowed
    assert metrics.count("auth_limiter_failed_open") == 1
    assert metrics.count("traffic_limiter_failed_open") == 0
    assert any(entry["event"] == "auth_failure_limiter.failed_open" for entry in logs)


async def test_sec9_lockout_visible_in_metrics(engine, redis):
    """SEC-9: a lockout shows in the exported metrics."""
    await seed_api_key(engine, SERVICE_KEY)
    settings = hermetic_settings(auth_failure_limit=1)
    async with _running(engine, redis, settings=settings) as (http, _app):
        bad = {"Authorization": "Bearer bmcp_ak_not_a_real_key_at_all_000000000000"}
        body = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        for _ in range(3):
            await http.post("/main/mcp", headers=bad, json=body)
        text = await _scrape(http)
    assert _sample(text, "bundlemcp_auth_lockouts_total") >= 1
    assert _sample(text, "bundlemcp_auth_failures_total") >= 2


async def _set_health(engine, server: str, status: HealthStatus) -> None:
    async with session_factory(engine)() as db:
        row = (
            await db.execute(select(McpServerRow).where(McpServerRow.name == server))
        ).scalar_one()
        row.health_status = status
        db.add(row)
        await db.commit()


async def test_ops11_unhealthy_member_marks_listing_degraded(engine, redis):
    """OPS-11: a listing that includes an unhealthy member still lists it, and is counted and
    logged as degraded for that member."""
    await seed_api_key(engine, SERVICE_KEY)
    async with _running(engine, redis) as (http, _app):
        await _set_health(engine, "notes", HealthStatus.ERROR)
        session = await _initialize(http)
        with capture_logs() as logs:
            listed = await _rpc(http, "main", session, "tools/list")
        text = await _scrape(http)
    names = {tool["name"] for tool in listed.json()["result"]["tools"]}
    assert "notes__write_note" in names and "echo__say" in names
    assert (
        _sample(text, "bundlemcp_tools_list_degraded_total", endpoint="main", server="notes") == 1
    )
    assert _sample(text, "bundlemcp_tools_list_degraded_total", endpoint="main", server="echo") == 0
    [warning] = [entry for entry in logs if entry["event"] == "tools_list.degraded"]
    assert warning["log_level"] == "warning"
    assert warning["endpoint"] == "main" and warning["server"] == "notes"


async def test_ops11_healthy_listing_not_degraded(engine, redis):
    await seed_api_key(engine, SERVICE_KEY)
    async with _running(engine, redis) as (http, _app):
        session = await _initialize(http)
        with capture_logs() as logs:
            await _rpc(http, "main", session, "tools/list")
        text = await _scrape(http)
    assert "bundlemcp_tools_list_degraded_total{" not in text
    assert not any(entry["event"] == "tools_list.degraded" for entry in logs)


async def test_sec10_metrics_labels_carry_no_secrets(engine, redis):
    """SEC-10: after calls with a key, a bearer and a forwarded header, the metrics hold none
    of them, nor the caller's sub or key id."""
    await seed_api_key(engine, SERVICE_KEY)
    tenant = "tenant-secret-value-123"
    async with _running(engine, redis) as (http, app):
        session = await _initialize(http)
        await _rpc(http, "main", session, "tools/call", SAY)
        await http.post(
            "/main/mcp",
            headers={"Mcp-Session-Id": session, "x-tenant": tenant},
            json={
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {"name": "notes__write_note", "arguments": {"text": "t"}},
            },
        )
        text = await _scrape(http)
    assert_redacted(text, [ENDPOINT_KEY, SERVICE_KEY, tenant, session])
    assert "sub=" not in text and "api_key_id" not in text


async def test_sec10_redaction_logs_and_error_bodies(engine, redis, capsys):
    """SEC-10: a rejected bad key appears neither in the log nor in the error body."""
    bad_key = "bmcp_ak_wrongwrongwrongwrongwrongwrongwrong0"
    async with _running(engine, redis) as (http, _app):
        capsys.readouterr()
        resp = await http.post(
            "/main/mcp",
            headers={"Authorization": f"Bearer {bad_key}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        logs = capsys.readouterr().err
    assert resp.status_code == 401
    assert_redacted(resp.text, [bad_key])
    assert_redacted(json.dumps(dict(resp.headers)), [bad_key])
    assert_redacted(logs, [bad_key])
