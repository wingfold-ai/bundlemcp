"""Cancelling an in-flight tool call, in either era and from any replica (PROT-3)."""

import asyncio
import json

import httpx
from bundlemcp.application.metering.meter_decision import MeterDecision
from bundlemcp.application.metering.meter_outcome import MeterOutcome
from bundlemcp.infrastructure.config.settings import EnvSettings
from bundlemcp.main.app import create_app
from bundlemcp.main.composition_overrides import CompositionOverrides
from httpx import AsyncClient

from tests.api.test_relay import (
    ENDPOINT_KEY,
    SERVICE_KEY,
    _initialize,
    _modern,
    running_app,
    seed,
    upstream_factory,
)


class OutcomeHook:
    """Records the outcome every metered call is reported with."""

    def __init__(self) -> None:
        self.outcomes: list[MeterOutcome] = []

    async def pre_call(self, ctx) -> MeterDecision:
        return MeterDecision(allowed=True)

    async def post_call(self, ctx, outcome, duration_ms) -> None:
        self.outcomes.append(outcome)


def _app(engine, redis, hook: OutcomeHook):
    settings = EnvSettings(_env_file=None, database_url="sqlite+aiosqlite://")
    return create_app(
        settings,
        overrides=CompositionOverrides(
            engine=engine, redis=redis, client_factory=upstream_factory, metering_hook=hook
        ),
    )


async def _modern_hang(
    http: AsyncClient, id_: int, seconds: float = 30, started: asyncio.Event | None = None
) -> dict:
    """A modern tools/call of the hanging tool; returns its final JSON-RPC message.

    ``started`` is set once the call's event stream has opened, which happens only after
    the call was admitted and registered.
    """
    body, headers = _modern(
        "tools/call", {"name": "relay__hang", "arguments": {"seconds": seconds}}, id_=id_
    )
    async with http.stream("POST", "/main/mcp", headers=headers, json=body) as resp:
        if started is not None:
            started.set()
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                message = json.loads(line[6:])
                if message.get("id") == id_:
                    return message
    raise AssertionError("the call ended without a final message")


async def _modern_cancel(base_url: str, key: str, request_id: int) -> int:
    body, headers = _modern("notifications/cancelled", {"requestId": request_id})
    body.pop("id")
    async with AsyncClient(base_url=base_url, headers={"Authorization": f"Bearer {key}"}) as c:
        resp = await c.post("/main/mcp", headers=headers, json=body)
    return resp.status_code


async def test_prot3_modern_cancel_from_the_same_caller_ends_the_call(engine, redis):
    """PROT-3: a modern notifications/cancelled sent in a separate request with the same
    credentials ends the named in-flight call, reported as cancelled."""
    await seed(engine)
    hook = OutcomeHook()
    async with running_app(_app(engine, redis, hook)) as base_url:
        async with AsyncClient(
            base_url=base_url, headers={"Authorization": f"Bearer {ENDPOINT_KEY}"}, timeout=10
        ) as http:
            call = asyncio.create_task(_modern_hang(http, 9))
            await asyncio.sleep(0.5)
            assert await _modern_cancel(base_url, ENDPOINT_KEY, 9) == 202
            final = await asyncio.wait_for(call, timeout=5)
    assert final["error"]["message"] == "cancelled"
    assert hook.outcomes == [MeterOutcome.CANCELLED]


async def test_prot3_modern_cancel_reaches_the_call_on_another_replica(engine, redis):
    """PROT-3: the call runs on replica A; the cancellation arrives at replica B."""
    await seed(engine)
    hook = OutcomeHook()
    async with running_app(_app(engine, redis, hook)) as base_a:
        async with running_app(_app(engine, redis, hook)) as base_b:
            async with AsyncClient(
                base_url=base_a, headers={"Authorization": f"Bearer {ENDPOINT_KEY}"}, timeout=10
            ) as http_a:
                call = asyncio.create_task(_modern_hang(http_a, 11))
                await asyncio.sleep(0.5)
                assert await _modern_cancel(base_b, ENDPOINT_KEY, 11) == 202
                final = await asyncio.wait_for(call, timeout=5)
    assert final["error"]["message"] == "cancelled"


async def test_prot3_another_caller_cannot_cancel(engine, redis):
    """PROT-3: a cancellation for the same request id from a different caller does not reach
    the call, which completes with its result."""
    await seed(engine)
    hook = OutcomeHook()
    async with running_app(_app(engine, redis, hook)) as base_url:
        async with AsyncClient(
            base_url=base_url, headers={"Authorization": f"Bearer {ENDPOINT_KEY}"}, timeout=10
        ) as http:
            call = asyncio.create_task(_modern_hang(http, 13, seconds=1.0))
            await asyncio.sleep(0.3)
            assert await _modern_cancel(base_url, SERVICE_KEY, 13) == 202
            final = await asyncio.wait_for(call, timeout=5)
    assert final["result"]["content"][0]["text"] == "finished"
    assert hook.outcomes == [MeterOutcome.RESULT]


async def test_prot3_disconnect_during_a_buffered_call_cancels_it(engine, redis):
    """PROT-3: a handshake client that calls without a progress token and goes away before
    the result ends the upstream call, which is reported as cancelled."""
    await seed(engine)
    hook = OutcomeHook()
    async with running_app(_app(engine, redis, hook)) as base_url:
        auth = {"Authorization": f"Bearer {ENDPOINT_KEY}"}
        async with AsyncClient(base_url=base_url, headers=auth, timeout=10) as http:
            session = await _initialize(http)
        async with AsyncClient(base_url=base_url, headers=auth, timeout=0.5) as impatient:
            try:
                await impatient.post(
                    "/main/mcp",
                    headers={"Mcp-Session-Id": session},
                    json={
                        "jsonrpc": "2.0",
                        "id": 5,
                        "method": "tools/call",
                        "params": {"name": "relay__hang", "arguments": {"seconds": 30}},
                    },
                )
            except httpx.ReadTimeout:
                pass  # the client gives up and closes the connection
        for _ in range(60):
            if hook.outcomes:
                break
            await asyncio.sleep(0.1)
    assert hook.outcomes == [MeterOutcome.CANCELLED]
