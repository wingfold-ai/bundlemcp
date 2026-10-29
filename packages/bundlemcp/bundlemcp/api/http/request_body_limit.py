"""The request body limit, enforced before a request body is parsed or admitted.

Runs as ASGI middleware, ahead of routing, on the MCP endpoints, the
management API and the OAuth server. A declared ``Content-Length`` over the
limit is refused before anything is read; a body without one (chunked) is
counted as it streams in and refused as soon as it crosses the limit, so at most
the limit plus one chunk is held in memory. The MCP and management limit is read
from the runtime-config snapshot, so the check costs no I/O. Paths under
``/oauth/`` answer before anyone signs in and carry only small forms and JSON, so
they get a fixed, smaller limit that no runtime setting raises.
"""

import re
from collections.abc import Callable

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bundlemcp.api.http.mcp_route_path import MCP_PATH
from bundlemcp.api.http.providers import current_request_limit

API_PATH = re.compile(r"^/api/v1(/|$)")
OAUTH_PATH = re.compile(r"^/oauth(/|$)")
# Real OAuth requests are under 4 KiB; this is also the smallest configurable request limit.
OAUTH_BODY_LIMIT = 64 * 1024
INVALID_REQUEST = -32600  # JSON-RPC: the request is not a valid request object


class BodyTooLarge(HTTPException):
    """A streamed body crossed the limit.

    An ``HTTPException`` so FastAPI, which turns any other error raised while
    it reads a body into a 400, passes it through; ``body_too_large_handler``
    renders it.
    """

    def __init__(self, limit: int) -> None:
        super().__init__(status_code=413)
        self.limit = limit


def too_large(path: str, limit: int) -> JSONResponse:
    """The 413 in the shape each surface's clients parse."""
    message = f"request body exceeds the {limit}-byte limit"
    if MCP_PATH.match(path):
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": INVALID_REQUEST, "message": message}},
            status_code=413,
        )
    if OAUTH_PATH.match(path):  # the RFC 6749 error object OAuth clients parse
        return JSONResponse(
            {"error": "invalid_request", "error_description": message}, status_code=413
        )
    return JSONResponse({"detail": message}, status_code=413)


class RequestBodyLimit:
    """ASGI middleware bounding request bodies on ``/{endpoint}/mcp``, ``/api/v1``, ``/oauth/``."""

    def __init__(self, app: ASGIApp, *, limit: Callable[[Scope], int] | None = None) -> None:
        self._app = app
        self._limit = limit or (lambda scope: current_request_limit(scope["app"]))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        limit = self._limit_for(path, scope) if scope["type"] == "http" else None
        if limit is None:
            await self._app(scope, receive, send)
            return
        if _declared_length(scope) > limit:
            await too_large(path, limit)(scope, receive, send)
            return

        received = 0
        started = False

        async def counted_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise BodyTooLarge(limit)
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self._app(scope, counted_receive, tracked_send)
        except BodyTooLarge:
            if started:  # a handler answered before reading the whole body; nothing to add
                return
            await too_large(path, limit)(scope, receive, send)

    def _limit_for(self, path: str, scope: Scope) -> int | None:
        """The byte limit for this path, or None for a path this middleware leaves alone."""
        if OAUTH_PATH.match(path):
            return OAUTH_BODY_LIMIT
        if API_PATH.match(path) or MCP_PATH.match(path):
            return self._limit(scope)
        return None


async def body_too_large_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render a body that crossed the limit while a route was reading it."""
    if not isinstance(exc, BodyTooLarge):
        raise TypeError(f"body_too_large_handler handles BodyTooLarge, not {type(exc).__name__}")
    return too_large(request.url.path, exc.limit)


def _declared_length(scope: Scope) -> int:
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return 0
    return 0
