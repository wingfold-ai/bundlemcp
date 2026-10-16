"""A valid credential not entitled to the endpoint is audited on tools/call (OPS-2)."""

from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.domain.shared.secrets import (
    API_KEY_PREFIX,
    display_prefix,
    generate_token,
    hash_token,
)
from bundlemcp.infrastructure.memory.recording_metrics import RecordingMetrics
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.api_key_row import ApiKeyRow
from bundlemcp.infrastructure.postgres.rows.audit_record_row import AuditRecordRow
from bundlemcp.infrastructure.postgres.rows.endpoint_row import EndpointRow
from sqlmodel import select

from tests.api.test_gateway import _initialize, _rpc, _running, _set_rate_limit

SAY = {"name": "echo__say", "arguments": {"text": "x"}}
CALL = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": SAY}
LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}


async def _key_scoped_to(engine, endpoint: str) -> tuple[str, str]:
    """A valid endpoint-kind key that reaches only ``endpoint``; its value and id."""
    key = generate_token(API_KEY_PREFIX)
    async with session_factory(engine)() as db:
        scope = (
            await db.execute(select(EndpointRow).where(EndpointRow.name == endpoint))
        ).scalar_one()
        row = ApiKeyRow(
            name="scoped",
            key_hash=hash_token(key),
            key_prefix=display_prefix(key),
            kind=ApiKeyKind.ENDPOINT,
            endpoint_ids=[str(scope.id)],
        )
        db.add(row)
        await db.commit()
        return key, str(row.id)


async def _records(app) -> list[AuditRecordRow]:
    await app.state.container.audit.drain()
    async with app.state.container.session_factory() as db:
        return list((await db.execute(select(AuditRecordRow))).scalars())


async def test_ops2_valid_key_wrong_endpoint_audited_forbidden(engine, redis):
    """OPS-2: a tools/call with a key scoped to gpt, on main, is refused as before and audited
    with the key's id, the presented tool, status denied and reason forbidden."""
    async with _running(engine, redis) as (http, app):
        key, key_id = await _key_scoped_to(engine, "gpt")
        resp = await http.post("/main/mcp", headers={"Authorization": f"Bearer {key}"}, json=CALL)
        [record] = await _records(app)
    assert resp.status_code == 401
    assert record.endpoint_name == "main" and str(record.api_key_id).replace(
        "-", ""
    ) == key_id.replace("-", "")
    assert record.presented_tool_name == "echo__say"
    assert record.status == "denied" and record.denied_reason == "forbidden"
    assert record.idempotency_key is None


async def test_ops2_forbidden_tools_list_not_audited(engine, redis):
    """OPS-2: the same key on tools/list is refused and leaves no record."""
    async with _running(engine, redis) as (http, app):
        key, _key_id = await _key_scoped_to(engine, "gpt")
        resp = await http.post("/main/mcp", headers={"Authorization": f"Bearer {key}"}, json=LIST)
        assert resp.status_code == 401
        assert await _records(app) == []


async def test_ops2_rate_limited_call_counted_not_audited(engine, redis):
    """OPS-2: a rate-limited call leaves no record, and the rejection metric rises."""
    metrics = RecordingMetrics()
    async with _running(engine, redis, metrics=metrics) as (http, app):
        await _set_rate_limit(app, {"endpoint": {"limit": 1, "window_seconds": 100}})
        session = await _initialize(http)
        await _rpc(http, "main", session, "tools/call", SAY)
        assert (await _rpc(http, "main", session, "tools/call", SAY)).status_code == 429
        records = await _records(app)
    assert [record.status for record in records] == ["success"]
    assert metrics.count("rate_limit_rejected") == 1


async def test_ops2_auth_failure_counted_not_audited(engine, redis):
    """OPS-2: a tools/call with an unknown key leaves no record, and the auth-failure metric
    rises."""
    metrics = RecordingMetrics()
    async with _running(engine, redis, metrics=metrics) as (http, app):
        unknown = generate_token(API_KEY_PREFIX)
        resp = await http.post(
            "/main/mcp", headers={"Authorization": f"Bearer {unknown}"}, json=CALL
        )
        assert resp.status_code == 401
        assert await _records(app) == []
    assert metrics.count("auth_failed") >= 1
