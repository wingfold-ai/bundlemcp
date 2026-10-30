"""A write that collides with a concurrent one answers 409, never an unhandled 500."""

import json
from contextlib import contextmanager

from bundlemcp.api.http.store_conflict_handler import store_conflict_handler
from bundlemcp.application.contracts.persistence.store_conflict import StoreConflict
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request


@contextmanager
def concurrent_insert_wins(engine):
    """Every INSERT fails as it does when another transaction stored the same key first."""

    def refuse(_conn, _cursor, statement, *_args, **_kwargs):
        if statement.lstrip().upper().startswith("INSERT"):
            raise IntegrityError(statement, {}, ValueError("duplicate key"))

    event.listen(engine.sync_engine, "before_cursor_execute", refuse)
    try:
        yield
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", refuse)


async def test_mgmt6_a_colliding_write_answers_409(engine, service_client):
    """MGMT-6: a create that loses a race on a unique key answers 409 with a retryable
    message, and the gateway keeps answering on the same connection."""
    with concurrent_insert_wins(engine):
        resp = await service_client.put(
            "/api/v1/upstreams/racer", json={"name": "racer", "url": "http://racer/mcp"}
        )
    assert resp.status_code == 409
    assert "retry" in resp.json()["detail"]
    assert (await service_client.get("/api/v1/upstreams/racer")).status_code == 404


async def test_mgmt6_a_conflict_on_an_mcp_path_is_a_json_rpc_error():
    """MGMT-6: an MCP endpoint reports the same conflict as a JSON-RPC error."""
    request = Request({"type": "http", "method": "POST", "path": "/main/mcp", "headers": []})

    resp = await store_conflict_handler(request, StoreConflict("uq_tools_server_name"))

    assert resp.status_code == 409
    assert json.loads(resp.body)["error"]["code"] == -32000
