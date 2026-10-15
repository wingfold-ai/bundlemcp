"""The cap on one upstream message (SEC-7)."""

import httpx2
import pytest
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.infrastructure.fastmcp.response_cap import CappedStream, UpstreamResponseTooLarge


class Chunks(httpx2.AsyncByteStream):
    def __init__(self, *chunks: bytes) -> None:
        self.chunks = chunks
        self.closed = False
        self.read = 0

    async def __aiter__(self):
        for chunk in self.chunks:
            self.read += 1
            yield chunk

    async def aclose(self):
        self.closed = True


async def drain(stream: CappedStream) -> bytes:
    return b"".join([chunk async for chunk in stream])


def event(size: int) -> bytes:
    return b"data: " + b"x" * (size - 8) + b"\n\n"


async def test_sec7_an_event_stream_is_capped_per_event():
    """SEC-7: a long-lived stream may carry far more than the cap, one small event at a time."""
    body = Chunks(*(event(60) for _ in range(50)))
    assert len(await drain(CappedStream(body, 100, events=True, log=None))) == 3000


async def test_sec7_one_oversized_event_is_abandoned_and_recorded():
    """SEC-7: the event crossing the cap closes the stream, records the cap, and stops reading."""
    body = Chunks(event(60), b"data: " + b"x" * 80, b"x" * 80, event(60))
    log = ResponseLog()
    with pytest.raises(UpstreamResponseTooLarge):
        await drain(CappedStream(body, 100, events=True, log=log))
    assert log.oversized_limit == 100
    assert body.closed
    assert body.read == 3  # the event after the oversized one is never read


async def test_sec7_a_boundary_split_across_chunks_still_resets():
    """SEC-7: an event boundary arriving in two chunks still starts a new count."""
    body = Chunks(b"data: " + b"x" * 80 + b"\n", b"\n" + b"data: " + b"x" * 80 + b"\n\n")
    assert await drain(CappedStream(body, 100, events=True, log=None))


async def test_sec7_a_json_body_is_capped_whole():
    """SEC-7: a JSON response is one message, counted in full."""
    body = Chunks(b"{" + b"x" * 60, b"x" * 60 + b"}")
    with pytest.raises(UpstreamResponseTooLarge):
        await drain(CappedStream(body, 100, events=False, log=None))


def test_sec7_the_production_mcp_client_caps_responses_behind_the_egress_guard():
    """SEC-7: the client the gateway uses toward upstreams carries the cap and the guard."""
    from bundlemcp.infrastructure.config.settings import EnvSettings
    from bundlemcp.infrastructure.egress.guarded_backend import GuardedNetworkBackend
    from bundlemcp.infrastructure.fastmcp.guarded_mcp_http_client import guarded_mcp_http_client
    from bundlemcp.infrastructure.fastmcp.response_cap import CappedResponses

    log = ResponseLog()
    client = guarded_mcp_http_client(
        EnvSettings(_env_file=None), response_cap=lambda: 1024, log=log
    )()
    capped = client._transport
    assert isinstance(capped, CappedResponses)
    assert isinstance(capped._inner._pool._network_backend, GuardedNetworkBackend)
