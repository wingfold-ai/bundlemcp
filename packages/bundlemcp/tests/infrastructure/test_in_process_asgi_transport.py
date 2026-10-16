"""The in-process transport the inspector reaches the gateway's own endpoints through."""

import asyncio

import httpx2
from bundlemcp.infrastructure.fastmcp.in_process_asgi_transport import InProcessAsgiTransport


def _app(release: asyncio.Event, seen: dict):
    async def app(scope, receive, send):
        seen["client"] = scope["client"]
        seen["body"] = (await receive())["body"]
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"first", "more_body": True})
        await release.wait()
        await send({"type": "http.response.body", "body": b"second", "more_body": False})

    return app


async def test_ui9_body_streams_before_the_app_finishes():
    """UI-9: the first chunk arrives while the app is still writing, so progress is live."""
    release, seen = asyncio.Event(), {}
    transport = InProcessAsgiTransport(_app(release, seen), client=("203.0.113.9", 0))
    async with httpx2.AsyncClient(transport=transport, base_url="http://gw") as client:
        async with client.stream("POST", "/e/mcp", content=b"{}") as response:
            chunks = response.aiter_bytes()
            first = await asyncio.wait_for(anext(chunks), timeout=1)
            release.set()
            rest = [chunk async for chunk in chunks]

    assert (first, rest) == (b"first", [b"second"])
    assert seen == {"client": ("203.0.113.9", 0), "body": b"{}"}


async def test_closing_the_response_disconnects_the_app():
    """A client that stops reading ends the app's request instead of leaving it running."""
    release = asyncio.Event()
    transport = InProcessAsgiTransport(_app(release, {}), client=("127.0.0.1", 0))
    async with httpx2.AsyncClient(transport=transport, base_url="http://gw") as client:
        async with client.stream("POST", "/e/mcp", content=b"") as response:
            assert await anext(response.aiter_bytes()) == b"first"
    # leaving the block closed the stream; the app is cancelled, not left waiting
    assert not release.is_set()
