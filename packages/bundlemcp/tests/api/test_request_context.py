"""Every log line of a request carries who and what it is about (OPS-8, DEP-2)."""

import asyncio
import json

from tests.api.test_gateway import _initialize, _rpc, _running
from tests.api.test_upstream_health_live_calls import SAY, SwitchableUpstreams
from tests.conftest import ENDPOINT_KEY, hermetic_settings


def _lines(capsys) -> list[dict]:
    lines = []
    for line in capsys.readouterr().err.splitlines():
        try:
            lines.append(json.loads(line))
        except ValueError:
            continue
    return lines


def _of(lines: list[dict], request_id: str) -> list[dict]:
    return [line for line in lines if line.get("request_id") == request_id]


async def test_ops8_request_id_returned_and_logged(engine, redis, capsys):
    """OPS-8: the X-Request-Id header is the request_id on that request's lines."""
    async with _running(engine, redis) as (http, _app):
        capsys.readouterr()
        resp = await http.get("/healthz")
        request_id = resp.headers["X-Request-Id"]
        [access] = [
            line for line in _of(_lines(capsys), request_id) if line["event"] == "http.request"
        ]
    assert access["status"] == 200 and access["path"] == "/healthz"


async def test_ops8_one_access_line_per_request(engine, redis, capsys):
    """OPS-8: one http.request line per request, and none from uvicorn's access logger."""
    async with _running(engine, redis) as (http, _app):
        capsys.readouterr()
        for _ in range(3):
            await http.get("/healthz")
        lines = _lines(capsys)
    assert sum(line["event"] == "http.request" for line in lines) == 3
    assert not any(line.get("logger") == "uvicorn.access" for line in lines)


async def test_dep2_logs_carry_derived_client_ip(engine, redis, capsys):
    """DEP-2: the client IP on a line is the one the trusted-proxy policy derives."""
    settings = hermetic_settings(trusted_proxies=["127.0.0.0/8"])
    async with _running(engine, redis, settings=settings) as (http, _app):
        capsys.readouterr()
        resp = await http.get("/healthz", headers={"X-Forwarded-For": "203.0.113.9"})
        [line] = _of(_lines(capsys), resp.headers["X-Request-Id"])
    assert line["client_ip"] == "203.0.113.9"


async def test_ops8_tool_call_lines_carry_request_context(engine, redis, capsys):
    """OPS-8: a failed call's lines carry the request id, endpoint, session, key id and client
    IP, and none the key itself."""
    upstreams = SwitchableUpstreams()
    async with _running(engine, redis, client_factory=upstreams) as (http, _app):
        session = await _initialize(http)
        upstreams.down = True
        capsys.readouterr()
        resp = await _rpc(http, "main", session, "tools/call", SAY)
        output = capsys.readouterr().err
    lines = _of([json.loads(line) for line in output.splitlines()], resp.headers["X-Request-Id"])
    [failure] = [line for line in lines if line["event"] == "upstream.call_failed"]
    assert failure["endpoint"] == "main" and failure["session_id"] == session
    assert failure["api_key_id"] and failure["auth_method"] == "api_key"
    assert failure["server"] == "echo" and failure["tool"] == "say"
    assert failure["client_ip"]
    assert ENDPOINT_KEY not in output


async def test_ops8_rejected_before_auth_has_no_caller(engine, redis, capsys):
    """OPS-8: a request refused before its credential is checked names no caller."""
    async with _running(engine, redis) as (http, _app):
        capsys.readouterr()
        resp = await http.post("/nowhere/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
        [line] = _of(_lines(capsys), resp.headers["X-Request-Id"])
    assert resp.status_code == 404
    assert "client_ip" in line
    assert not {"user_id", "api_key_id", "auth_method"} & set(line)


async def test_ops8_context_does_not_leak_between_concurrent_requests(engine, redis, capsys):
    """OPS-8: two requests served at once each carry only their own id and endpoint."""
    async with _running(engine, redis) as (http, _app):
        main = await _initialize(http, "main")
        gpt = await _initialize(http, "gpt")
        capsys.readouterr()
        first, second = await asyncio.gather(
            _rpc(http, "main", main, "tools/list"), _rpc(http, "gpt", gpt, "tools/list")
        )
        lines = _lines(capsys)
    for resp, endpoint, session in ((first, "main", main), (second, "gpt", gpt)):
        mine = _of(lines, resp.headers["X-Request-Id"])
        assert mine
        assert {line["endpoint"] for line in mine} == {endpoint}
        assert {line["session_id"] for line in mine} == {session}
