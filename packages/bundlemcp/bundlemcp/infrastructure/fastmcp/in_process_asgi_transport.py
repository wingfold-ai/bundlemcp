"""An HTTP transport that serves requests from an ASGI app in this process, streaming."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx2
from starlette.types import ASGIApp, Message


class InProcessAsgiTransport(httpx2.AsyncBaseTransport):
    """Hands each request to ``app`` and streams its response body as the app sends it.

    httpx's own ASGI transport collects the whole body before returning, which
    would hold a Server-Sent Events stream until it ends; this one returns once
    the app has started its response. Closing the response tells the app the
    client disconnected. ``client`` is the peer address the app sees.
    """

    def __init__(self, app: ASGIApp, *, client: tuple[str, int]) -> None:
        self._app = app
        self._client = client

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        body = await request.aread()
        url = request.url
        scope: dict[str, Any] = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": request.method,
            "headers": [(key.lower(), value) for key, value in request.headers.raw],
            "scheme": url.scheme,
            "path": url.path,
            "raw_path": url.raw_path.split(b"?", 1)[0],
            "query_string": url.query,
            "root_path": "",
            "server": (url.host, url.port or (443 if url.scheme == "https" else 80)),
            "client": self._client,
        }
        chunks: asyncio.Queue[bytes | None] = asyncio.Queue()
        started = asyncio.Event()
        disconnected = asyncio.Event()
        response: dict[str, Any] = {}
        body_sent = False

        async def receive() -> Message:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            if message["type"] == "http.response.start":
                response["status"] = message["status"]
                response["headers"] = message.get("headers", [])
                started.set()
            elif message["type"] == "http.response.body":
                if chunk := message.get("body", b""):
                    chunks.put_nowait(chunk)
                if not message.get("more_body", False):
                    chunks.put_nowait(None)

        async def run() -> None:
            try:
                await self._app(scope, receive, send)
            finally:
                started.set()
                chunks.put_nowait(None)

        task = asyncio.create_task(run())
        await started.wait()
        if "status" not in response:
            await task  # the app failed before answering: raise what it raised
            raise httpx2.RemoteProtocolError("the app sent no response", request=request)
        return httpx2.Response(
            response["status"],
            headers=response["headers"],
            stream=_AppResponseStream(chunks, task, disconnected),
            request=request,
        )


class _AppResponseStream(httpx2.AsyncByteStream):
    def __init__(
        self, chunks: asyncio.Queue[bytes | None], task: asyncio.Task, disconnected: asyncio.Event
    ) -> None:
        self._chunks = chunks
        self._task = task
        self._disconnected = disconnected

    async def __aiter__(self) -> AsyncIterator[bytes]:
        while (chunk := await self._chunks.get()) is not None:
            yield chunk

    async def aclose(self) -> None:
        self._disconnected.set()
        if not self._task.done():
            self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
