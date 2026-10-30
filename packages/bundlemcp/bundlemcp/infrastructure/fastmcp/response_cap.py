"""The cap on one upstream message, applied while the response streams in.

A Streamable HTTP response is either one JSON body or an event stream that may
stay open for a session's lifetime, so the cap is per message: per JSON body,
and per server-sent event, the count starting again at each event boundary. A
message that crosses it is abandoned: the stream is closed, the overflow is
recorded on the connection's response log, and the read fails.
"""

import re
from collections.abc import AsyncIterator, Callable

import httpx2

from bundlemcp.domain.servers.response_log import ResponseLog

EVENT_BOUNDARY = re.compile(rb"\r\n\r\n|\n\n|\r\r")
BOUNDARY_TAIL = 3  # bytes kept so a boundary split across two chunks is still seen


class UpstreamResponseTooLarge(httpx2.TransportError):
    """One upstream message crossed the response cap."""


class CappedStream(httpx2.AsyncByteStream):
    """A response body that fails once one message in it crosses ``limit`` bytes."""

    def __init__(
        self, inner: httpx2.AsyncByteStream, limit: int, *, events: bool, log: ResponseLog | None
    ) -> None:
        self._inner = inner
        self._limit = limit
        self._events = events
        self._log = log
        self._count = 0
        self._tail = b""

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._inner:
            self._measure(chunk)
            if self._count > self._limit:
                await self.aclose()
                if self._log is not None:
                    self._log.record_oversized(self._limit)
                raise UpstreamResponseTooLarge(
                    f"upstream message exceeds the {self._limit}-byte limit"
                )
            yield chunk

    def _measure(self, chunk: bytes) -> None:
        if not self._events:
            self._count += len(chunk)
            return
        window = self._tail + chunk
        boundaries = list(EVENT_BOUNDARY.finditer(window))
        if boundaries:
            # bytes of the event still open after the last boundary
            self._count = len(window) - boundaries[-1].end()
        else:
            self._count += len(chunk)
        self._tail = window[-BOUNDARY_TAIL:]

    async def aclose(self) -> None:
        await self._inner.aclose()


class CappedResponses(httpx2.AsyncBaseTransport):
    """A transport whose responses are capped per message."""

    def __init__(
        self,
        inner: httpx2.AsyncBaseTransport,
        limit: Callable[[], int],
        log: ResponseLog | None = None,
    ) -> None:
        self._inner = inner
        self._limit = limit
        self._log = log

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        response = await self._inner.handle_async_request(request)
        content_type = response.headers.get("content-type", "").lower()
        if not isinstance(response.stream, httpx2.AsyncByteStream):
            raise TypeError(
                f"an async transport returned a {type(response.stream).__name__} stream"
            )
        response.stream = CappedStream(
            response.stream,
            self._limit(),
            events=content_type.startswith("text/event-stream"),
            log=self._log,
        )
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()
