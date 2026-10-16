"""One log context per HTTP request, and one access line for it."""

import time
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bundlemcp.api.http.client_ip import client_ip
from bundlemcp.application.settings.settings import Settings

log = structlog.get_logger("bundlemcp.api.http.access")

REQUEST_ID_HEADER = "X-Request-Id"


class RequestContextMiddleware:
    """Starts every request's log context with a request id and the client IP.

    A plain ASGI middleware, so the endpoint runs in this task and the fields it
    binds later (endpoint, session, caller) are visible here too. The context
    is cleared before and after each request, so nothing leaks into the next
    one. The request id goes back to the client as ``X-Request-Id``; one
    ``http.request`` line per request replaces uvicorn's access line, whose
    client address would be the proxy's.
    """

    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        self.app = app
        self._settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        structlog.contextvars.clear_contextvars()
        request_id = uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(
            request_id=request_id, client_ip=client_ip(Request(scope), self._settings)
        )
        started = time.monotonic()
        status = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            route = scope.get("route")
            log.info(
                "http.request",
                method=scope["method"],
                path=getattr(route, "path", scope["path"]),
                status=status,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            structlog.contextvars.clear_contextvars()
