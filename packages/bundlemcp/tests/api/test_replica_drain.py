"""A stopping replica drains within its window (SES-11)."""

import asyncio

from bundlemcp.application.metering.meter_outcome import MeterOutcome
from bundlemcp.infrastructure.config.settings import EnvSettings
from bundlemcp.main.app import create_app
from bundlemcp.main.composition_overrides import CompositionOverrides
from httpx import AsyncClient

from tests.api.test_cancellation import OutcomeHook, _modern_hang
from tests.api.test_relay import ENDPOINT_KEY, _modern, running_app, seed, upstream_factory


def _app(engine, redis, hook: OutcomeHook, *, drain_seconds: int):
    settings = EnvSettings(
        _env_file=None, database_url="sqlite+aiosqlite://", shutdown_drain_seconds=drain_seconds
    )
    return create_app(
        settings,
        overrides=CompositionOverrides(
            engine=engine, redis=redis, client_factory=upstream_factory, metering_hook=hook
        ),
    )


async def test_ses11_a_draining_replica_is_not_ready_and_refuses_new_requests(engine, redis):
    """SES-11: once draining, /readyz answers 503 and a new MCP request 503 with Retry-After."""
    await seed(engine)
    app = _app(engine, redis, OutcomeHook(), drain_seconds=10)
    async with running_app(app) as base_url:
        async with AsyncClient(
            base_url=base_url, headers={"Authorization": f"Bearer {ENDPOINT_KEY}"}
        ) as http:
            assert (await http.get("/readyz")).status_code == 200
            app.state.container.drain.begin()
            assert (await http.get("/readyz")).status_code == 503
            body, headers = _modern("tools/list", {})
            refused = await http.post("/main/mcp", headers=headers, json=body)
            assert refused.status_code == 503
            assert refused.headers["Retry-After"] == "1"
            assert refused.json()["error"]["code"] == -32000


async def test_ses11_an_in_flight_call_completes_during_the_drain(engine, redis):
    """SES-11: a call already running when the drain starts still returns its result."""
    await seed(engine)
    hook = OutcomeHook()
    app = _app(engine, redis, hook, drain_seconds=10)
    async with running_app(app) as base_url:
        async with AsyncClient(
            base_url=base_url, headers={"Authorization": f"Bearer {ENDPOINT_KEY}"}, timeout=10
        ) as http:
            call = asyncio.create_task(_modern_hang(http, 7, seconds=1))
            await asyncio.sleep(0.4)
            app.state.container.drain.begin()
            message = await asyncio.wait_for(call, timeout=5)
    assert "result" in message and not message["result"].get("isError")
    assert hook.outcomes == [MeterOutcome.RESULT]


async def test_ses11_a_call_still_running_at_the_drain_deadline_is_cancelled(engine, redis):
    """SES-11: a call outlasting the window ends with a structured error, metered cancelled."""
    await seed(engine)
    hook = OutcomeHook()
    app = _app(engine, redis, hook, drain_seconds=2)
    async with running_app(app) as base_url:
        async with AsyncClient(
            base_url=base_url, headers={"Authorization": f"Bearer {ENDPOINT_KEY}"}, timeout=10
        ) as http:
            started = asyncio.Event()
            call = asyncio.create_task(_modern_hang(http, 8, seconds=30, started=started))
            await asyncio.wait_for(started.wait(), timeout=10)  # admitted before the drain
            app.state.container.drain.begin()
            message = await asyncio.wait_for(call, timeout=5)
    assert "error" in message
    assert hook.outcomes == [MeterOutcome.CANCELLED]
