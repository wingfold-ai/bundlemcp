"""Adding the current lease's headers to each request of a pooled upstream transport."""

from collections.abc import Generator

import httpx2

from bundlemcp.infrastructure.fastmcp.lease_slot import LeaseSlot
from bundlemcp.infrastructure.fastmcp.response_observer import ResponseObserver


class LeaseHeaders(httpx2.Auth):
    """Puts the lease's caller headers on each request, then observes the answer.

    Installed as a pooled transport's auth hook, so a transport built once
    still sends each request with the credentials of the request it serves:
    a refreshed bearer or a freshly minted delegated token reaches the
    upstream without a new session. Header values live only in the slot.
    """

    def __init__(self, slot: LeaseSlot, observer: ResponseObserver) -> None:
        self._slot = slot
        self._observer = observer

    def auth_flow(self, request: httpx2.Request) -> Generator[httpx2.Request, httpx2.Response]:
        for name, value in self._slot.request_headers().items():
            request.headers[name] = value
        yield from self._observer.auth_flow(request)
