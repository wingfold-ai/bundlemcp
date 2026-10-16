"""Noting on a response log when the connection itself failed."""

from collections.abc import AsyncIterator

import httpx2

from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.infrastructure.fastmcp.response_cap import UpstreamResponseTooLarge


class RecordedStream(httpx2.AsyncByteStream):
    """A response body that notes on the log when reading it fails below HTTP."""

    def __init__(self, inner: httpx2.AsyncByteStream, log: ResponseLog) -> None:
        self._inner = inner
        self._log = log

    async def __aiter__(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self._inner:
                yield chunk
        except UpstreamResponseTooLarge:
            raise  # the gateway's own limit, recorded by the cap
        except httpx2.TransportError:
            self._log.record_transport_failure()
            raise

    async def aclose(self) -> None:
        await self._inner.aclose()


class RecordedTransportFailures(httpx2.AsyncBaseTransport):
    """A transport that notes on ``log`` every request or stream that failed to connect or read.

    The MCP client reports a refused connection and a server's error the same
    way; the log lets the caller tell an upstream that could not be reached
    from one that answered.
    """

    def __init__(self, inner: httpx2.AsyncBaseTransport, log: ResponseLog) -> None:
        self._inner = inner
        self._log = log

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        try:
            response = await self._inner.handle_async_request(request)
        except UpstreamResponseTooLarge:
            raise
        except (httpx2.TransportError, OSError):
            self._log.record_transport_failure()
            raise
        assert isinstance(response.stream, httpx2.AsyncByteStream)
        response.stream = RecordedStream(response.stream, self._log)
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()
