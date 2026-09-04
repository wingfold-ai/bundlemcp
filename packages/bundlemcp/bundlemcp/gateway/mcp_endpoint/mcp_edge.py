"""The Streamable-HTTP edge: admit the caller, find the session, hand the message on.

Implemented directly rather than through FastMCP's server session manager so
that session state lives in Valkey and any replica serves any request. FastMCP
is used for the upstream side only.
"""

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bundlemcp.gateway.composition import load_bundle_view
from bundlemcp.gateway.mcp_endpoint.authentication import (
    EndpointAuthentication,
    unauthorized_challenge,
)
from bundlemcp.gateway.mcp_endpoint.endpoint_context import EndpointContext
from bundlemcp.gateway.mcp_endpoint.handlers import SESSION_HEADER
from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_error
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.mcp_endpoint.method_handler import MethodHandler
from bundlemcp.gateway.mcp_endpoint.method_registry import MethodRegistry
from bundlemcp.gateway.mcp_endpoint.request_rejected import RequestRejected
from bundlemcp.gateway.mcp_endpoint.session_context import SessionContext
from bundlemcp.gateway.ratelimit import AuthFailureGuard
from bundlemcp.gateway.signals import SignalBus
from bundlemcp.gateway.streams import StreamRegistry
from bundlemcp.store.sessions import SessionRecord, SessionStore

PARSE_ERROR = -32700
KEEPALIVE_SECONDS = 15
SSE_HEADERS = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}


class McpEdge:
    """Serves POST, GET and DELETE on ``/{endpoint}/mcp`` for every endpoint."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        sessions: SessionStore,
        registry: StreamRegistry,
        signals: SignalBus,
        authentication: EndpointAuthentication,
        auth_failures: AuthFailureGuard,
        initialize: MethodHandler[EndpointContext],
        methods: MethodRegistry,
        public_base: str,
    ) -> None:
        self._session_factory = session_factory
        self._sessions = sessions
        self._registry = registry
        self._signals = signals
        self._authentication = authentication
        self._auth_failures = auth_failures
        self._initialize = initialize
        self._methods = methods
        self._public_base = public_base

    async def post(self, request: Request, endpoint_name: str) -> Response:
        try:
            ctx = await self._admit(request, endpoint_name)
            message = await self._parse(request)
            if message.method == "initialize":
                return await self._initialize.handle(ctx, message)
            session = await self._session_of(request, endpoint_name)
        except RequestRejected as rejected:
            return rejected.response

        await self._sessions.touch(session.session_id)  # SES-1 (+ PROT-8 for ping)
        session_ctx = SessionContext(
            request=ctx.request, view=ctx.view, identity=ctx.identity, session=session
        )
        if message.is_response:
            # PROT-4: the client's reply to a server->client request — route it
            # to the awaiting call.
            if message.id is not None:
                await self._signals.reply(str(message.id), message.body())
            return Response(status_code=202)
        return await self._methods.dispatch(session_ctx, message)

    async def close_session(self, request: Request, endpoint_name: str) -> Response:
        """Explicit session termination."""
        session_id = request.headers.get(SESSION_HEADER, "")
        if session_id:
            await self._sessions.delete(session_id)
        return Response(status_code=204)

    async def open_stream(self, request: Request, endpoint_name: str) -> Response:
        """The server->client event stream (SSE).

        Carries list_changed notifications and server->client requests. The open
        stream is replica-pinned; messages from other replicas arrive via the
        signal bus.
        """
        try:
            await self._admit(request, endpoint_name)
            session = await self._session_of(request, endpoint_name)
        except RequestRejected as rejected:
            return rejected.response
        queue = self._registry.register_stream(session.session_id)
        return StreamingResponse(
            self._events(session.session_id, queue),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    async def _events(self, session_id: str, queue: asyncio.Queue) -> AsyncIterator[str]:
        try:
            yield ": connected\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                    yield f"data: {json.dumps(payload)}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
                    await self._sessions.touch(session_id)  # stream open = active
        finally:
            self._registry.unregister_stream(session_id, queue)

    async def _admit(self, request: Request, endpoint_name: str) -> EndpointContext:
        """Resolve the endpoint and authenticate the caller, or reject the request."""
        async with self._session_factory() as db:
            view = await load_bundle_view(db, endpoint_name)
            if view is None:
                raise RequestRejected(JSONResponse({"error": "not found"}, status_code=404))
            identity = await self._authentication.authenticate(request, db, view)
        if identity is None:
            locked = await self._auth_failures.note_failure(request)  # RATE-5
            raise RequestRejected(
                locked or unauthorized_challenge(self._public_base, endpoint_name)
            )
        return EndpointContext(request=request, view=view, identity=identity)

    @staticmethod
    async def _parse(request: Request) -> JsonRpcMessage:
        try:
            return JsonRpcMessage.parse(await request.json())
        except (ValueError, ValidationError):
            raise RequestRejected(rpc_error(None, PARSE_ERROR, "parse error", status=400)) from None

    async def _session_of(self, request: Request, endpoint_name: str) -> SessionRecord:
        # SES-2/SES-3: everything but initialize requires a live session record
        session_id = request.headers.get(SESSION_HEADER, "")
        record = await self._sessions.load(session_id) if session_id else None
        if record is None or record.endpoint_name != endpoint_name:
            raise RequestRejected(JSONResponse({"error": "session not found"}, status_code=404))
        return record
