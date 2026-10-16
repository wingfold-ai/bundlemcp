"""A FastMCP server on a loopback port that records what reaches it.

The pooled upstream sessions speak real Streamable HTTP — session ids, the
GET stream, ``DELETE`` — which an in-memory transport does not, so tests of
pooling serve the upstream over uvicorn and watch it from an ASGI wrapper.
"""

import asyncio
import contextlib
import json
import socket
from collections.abc import AsyncIterator
from typing import Any

import uvicorn
from fastmcp import FastMCP
from pydantic import BaseModel, Field
from sse_starlette.sse import AppStatus

SESSION_HEADER = b"mcp-session-id"


class SeenRequest(BaseModel):
    """One HTTP request the upstream received."""

    method: str = Field(description="HTTP method")
    rpc_method: str | None = Field(description="JSON-RPC method of a POST, if it named one")
    session_id: str | None = Field(description="The Mcp-Session-Id it carried")
    headers: dict[str, str] = Field(description="Its headers, lower-cased names")


class RecordingUpstream:
    """An ASGI wrapper around a FastMCP app: records requests and can forget sessions.

    ``forget()`` makes the upstream answer 404 for every session it has
    issued so far, as an upstream that restarted would; ``amnesiac`` makes it
    answer 404 for every session, as one that loses them at once would.
    """

    def __init__(self, server: FastMCP) -> None:
        self.app = server.http_app(path="/mcp")
        self.seen: list[SeenRequest] = []
        self.forgotten: set[str] = set()
        self.issued: set[str] = set()
        self.amnesiac = False

    def initializes(self) -> int:
        return sum(1 for request in self.seen if request.rpc_method == "initialize")

    def calls(self, rpc_method: str) -> list[SeenRequest]:
        return [request for request in self.seen if request.rpc_method == rpc_method]

    def deletes(self) -> list[SeenRequest]:
        return [request for request in self.seen if request.method == "DELETE"]

    def forget(self) -> None:
        self.forgotten |= self.issued

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {name.decode().lower(): value.decode() for name, value in scope["headers"]}
        session_id = headers.get("mcp-session-id")
        body = b""
        if scope["method"] == "POST":
            more = True
            while more:
                message = await receive()
                body += message.get("body", b"")
                more = message.get("more_body", False)
        rpc_method = None
        if body:
            with contextlib.suppress(ValueError, AttributeError):
                rpc_method = json.loads(body).get("method")
        self.seen.append(
            SeenRequest(
                method=scope["method"],
                rpc_method=rpc_method,
                session_id=session_id,
                headers=headers,
            )
        )
        if session_id is not None and (self.amnesiac or session_id in self.forgotten):
            await send({"type": "http.response.start", "status": 404, "headers": []})
            await send({"type": "http.response.body", "body": b""})
            return

        replayed = False

        async def replay() -> dict[str, Any]:
            nonlocal replayed
            if scope["method"] == "POST" and not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        async def watch(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                for name, value in message.get("headers", []):
                    if name.lower() == SESSION_HEADER:
                        self.issued.add(value.decode())
            await send(message)

        await self.app(scope, replay, watch)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.asynccontextmanager
async def serving_upstream(upstream: RecordingUpstream) -> AsyncIterator[str]:
    """Serve ``upstream`` on loopback; yields its MCP URL."""
    async with serving_app(upstream) as base_url:
        yield f"{base_url}/mcp"


@contextlib.asynccontextmanager
async def serving_app(app: Any) -> AsyncIterator[str]:
    """Serve an ASGI app on loopback, with real streaming; yields its base URL."""
    port = free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    try:
        for _ in range(250):
            if server.started:
                break
            await asyncio.sleep(0.02)
        assert server.started, "uvicorn did not start"
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(task, timeout=5)
        # the event-stream library notes a server's shutdown process-wide, and would
        # end every stream of the next server at once
        AppStatus.should_exit = False
