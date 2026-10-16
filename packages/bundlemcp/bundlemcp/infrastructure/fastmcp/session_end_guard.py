"""Keeping an upstream session alive when the transport that used it closes."""

import httpx2


class SessionEndGuard(httpx2.AsyncBaseTransport):
    """Answers the transport's own closing ``DELETE`` locally.

    The MCP client ends its upstream session whenever its transport closes.
    A pooled session outlives its transport — another transport, on this
    replica or another, may continue it — so ending one is a request of its
    own, sent only when the session is meant to end.
    """

    def __init__(self, inner: httpx2.AsyncBaseTransport) -> None:
        self._inner = inner

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        if request.method == "DELETE":
            return httpx2.Response(204, request=request)
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()
