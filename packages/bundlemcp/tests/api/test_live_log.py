"""The live log routes, and events reaching the buffer from requests (OPS-15, ARC-8)."""

import asyncio
import json

import httpx
from bundlemcp.application.contracts.live_state.live_log_entry import LiveLogEntry
from bundlemcp.infrastructure.memory.in_memory_live_log_buffer import InMemoryLiveLogBuffer
from bundlemcp.main.app import create_app
from bundlemcp.main.composition_overrides import CompositionOverrides

from tests.conftest import SERVICE_KEY, hermetic_settings, seed_api_key, serving
from tests.loopback_upstream import serving_app


async def _until(predicate, timeout: float = 5.0) -> None:
    for _ in range(int(timeout / 0.05)):
        if predicate():
            return
        await asyncio.sleep(0.05)
    assert predicate()


async def test_arc8_an_event_logged_during_a_request_reaches_the_buffer(engine, redis):
    """ARC-8, OPS-14: the request's access line lands in the shared buffer, not process memory."""
    await seed_api_key(engine, SERVICE_KEY)
    buffer = InMemoryLiveLogBuffer()
    async with serving(engine, redis, bearer=SERVICE_KEY, live_log_buffer=buffer) as (http, _):
        await http.get("/api/v1/bundles")
        await _until(lambda: any(e.event == "http.request" for e in buffer.entries))
    request = next(e for e in buffer.entries if e.event == "http.request")
    assert request.replica and request.fields["path"] == "/bundles"  # the route template


async def test_ops17_a_credential_never_reaches_the_buffer(engine, redis):
    """OPS-17: the service key and the Authorization header appear in no buffer entry."""
    await seed_api_key(engine, SERVICE_KEY)
    buffer = InMemoryLiveLogBuffer()
    async with serving(engine, redis, bearer=SERVICE_KEY, live_log_buffer=buffer) as (http, _):
        await http.get("/api/v1/upstreams", headers={"X-API-Key": SERVICE_KEY})
        await _until(lambda: any(e.event == "http.request" for e in buffer.entries))
    assert SERVICE_KEY not in json.dumps([e.model_dump() for e in buffer.entries])


async def test_ops15_recent_entries_are_filtered_and_need_credentials(engine, redis):
    """OPS-15: the backfill applies the filters, and nobody unauthenticated reads it."""
    await seed_api_key(engine, SERVICE_KEY)
    buffer = InMemoryLiveLogBuffer()
    await buffer.append(
        [
            LiveLogEntry(
                timestamp="t", level="error", event="boom", replica="r", endpoint="b1-api"
            ),
            LiveLogEntry(timestamp="t", level="info", event="fine", replica="r", endpoint="b1-api"),
        ]
    )
    async with serving(engine, redis, bearer=SERVICE_KEY, live_log_buffer=buffer) as (http, _):
        resp = await http.get("/api/v1/logs", params={"endpoint": "b1-api", "level": "error"})
        assert resp.status_code == 200
        assert [e["event"] for e in resp.json()] == ["boom"]
        anonymous = await http.get("/api/v1/logs", headers={"Authorization": ""})
        assert anonymous.status_code == 401
        stream = await http.get("/api/v1/logs/stream", headers={"Authorization": ""})
        assert stream.status_code == 401


async def test_ops15_the_stream_resumes_after_the_last_entry_seen(engine, redis):
    """OPS-15: a stream opened after a pause continues in order, without duplicates."""
    await seed_api_key(engine, SERVICE_KEY)
    buffer = InMemoryLiveLogBuffer()
    await buffer.append([LiveLogEntry(timestamp="t", level="info", event="seen", replica="r")])
    paused_at = buffer.entries[-1].id
    app = create_app(
        hermetic_settings(),
        overrides=CompositionOverrides(engine=engine, redis=redis, live_log_buffer=buffer),
    )
    async with serving_app(app) as base_url:
        await buffer.append(
            [
                LiveLogEntry(timestamp="t", level="info", event=f"missed-{n}", replica="r")
                for n in range(3)
            ]
        )
        received: list[dict] = []
        async with httpx.AsyncClient(
            base_url=base_url, headers={"Authorization": f"Bearer {SERVICE_KEY}"}, timeout=10
        ) as http:
            async with http.stream(
                "GET",
                "/api/v1/logs/stream",
                headers={"Last-Event-ID": paused_at},
                params={"q": "missed"},
            ) as resp:
                assert resp.status_code == 200
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        received.append(json.loads(line[6:]))
                        if len(received) == 3:
                            break
    assert [e["event"] for e in received] == ["missed-0", "missed-1", "missed-2"]


async def test_ops15_streams_beyond_the_cap_are_refused(engine, redis, monkeypatch):
    """OPS-15: a replica serves a bounded number of live streams and answers 429 beyond it."""
    from bundlemcp.api.management.controllers import live_log_controller

    monkeypatch.setattr(live_log_controller, "MAX_STREAMS", 0)
    await seed_api_key(engine, SERVICE_KEY)
    async with serving(
        engine, redis, bearer=SERVICE_KEY, live_log_buffer=InMemoryLiveLogBuffer()
    ) as (http, _):
        assert (await http.get("/api/v1/logs/stream")).status_code == 429
