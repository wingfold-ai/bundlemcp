"""A Postgres outage answers 503 with Retry-After, never 401 or 500 (SES-14)."""

from contextlib import contextmanager

from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from tests.api.test_gateway import _initialize, _rpc, _running


@contextmanager
def database_down(engine):
    """Every statement fails the way a lost connection does, until the block ends."""

    def refuse(*_args, **_kwargs):
        raise OperationalError("SELECT 1", {}, ConnectionRefusedError("connection refused"))

    event.listen(engine.sync_engine, "before_cursor_execute", refuse)
    try:
        yield
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", refuse)


async def test_ses14_a_valid_key_during_an_outage_gets_503_not_401(engine, redis):
    """SES-14: tools/list with a valid API key answers a retryable JSON-RPC 503."""
    async with _running(engine, redis) as (http, _app):
        session = await _initialize(http)
        with database_down(engine):
            resp = await _rpc(http, "main", session, "tools/list")
        assert resp.status_code == 503
        assert resp.headers["Retry-After"] == "2"
        assert resp.json()["error"]["code"] == -32000
        assert (await _rpc(http, "main", session, "tools/list")).status_code == 200


async def test_ses14_a_config_change_during_an_outage_gets_503(engine, redis):
    """SES-14: a management write while Postgres is down answers 503."""
    async with _running(engine, redis) as (http, _app):
        with database_down(engine):
            resp = await http.put(
                "/api/v1/upstreams/echo", json={"name": "echo", "url": "http://echo/mcp"}
            )
            ready = await http.get("/readyz")
        assert resp.status_code == 503 and "Retry-After" in resp.headers
        assert ready.status_code == 503


async def test_ses14_the_size_gate_still_answers_first(engine, redis):
    """SES-14: an oversized body is refused with 413 before anything asks the database."""
    async with _running(engine, redis) as (http, _app):
        with database_down(engine):
            resp = await http.post(
                "/main/mcp",
                content=b"x" * (5 * 1024 * 1024),
                headers={"content-type": "application/json"},
            )
        assert resp.status_code == 413
