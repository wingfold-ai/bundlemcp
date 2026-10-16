"""Audit records carry the metering idempotency key, the reconciliation join (OPS-7)."""

from tests.api.test_gateway import RecordingHook, _initialize, _rpc, _running
from tests.conftest import SERVICE_KEY, seed_api_key

SAY = {"name": "echo__say", "arguments": {"text": "x"}}


async def _records(http, app, **params) -> list[dict]:
    await app.state.container.audit.drain()
    resp = await http.get(
        "/api/v1/audit-records",
        params=params,
        headers={"Authorization": f"Bearer {SERVICE_KEY}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


async def test_ops7_record_carries_idempotency_key(engine, redis):
    """OPS-7: the terminal record has the key the pre-call hook received."""
    await seed_api_key(engine, SERVICE_KEY)
    hook = RecordingHook()
    async with _running(engine, redis, metering_hook=hook) as (http, app):
        session = await _initialize(http)
        await _rpc(http, "main", session, "tools/call", SAY)
        [record] = await _records(http, app)
    [context] = hook.pre_calls
    assert record["idempotency_key"] == context.idempotency_key


async def test_ops7_list_filters_by_idempotency_key(engine, redis):
    """OPS-7: listing with idempotency_key=K returns that invocation's record only."""
    await seed_api_key(engine, SERVICE_KEY)
    hook = RecordingHook()
    async with _running(engine, redis, metering_hook=hook) as (http, app):
        session = await _initialize(http)
        await _rpc(http, "main", session, "tools/call", SAY)
        await _rpc(http, "main", session, "tools/call", SAY, id_=3)
        first_key = hook.pre_calls[0].idempotency_key
        matching = await _records(http, app, idempotency_key=first_key)
        everything = await _records(http, app)
    assert [record["idempotency_key"] for record in matching] == [first_key]
    assert len(everything) == 2


async def test_ops7_unmetered_denial_has_no_key(engine, redis):
    """OPS-7: a call denied as an unknown tool, before any pre-call, has no key."""
    await seed_api_key(engine, SERVICE_KEY)
    async with _running(engine, redis) as (http, app):
        session = await _initialize(http)
        await _rpc(http, "main", session, "tools/call", {"name": "nope__nothing", "arguments": {}})
        [record] = await _records(http, app)
    assert record["status"] == "denied" and record["idempotency_key"] is None
