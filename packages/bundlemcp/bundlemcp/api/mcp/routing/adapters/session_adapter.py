"""Session-based MCP adapter: initialize handshake, Mcp-Session-Id in Valkey."""

from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from mcp.types import INVALID_PARAMS

from bundlemcp.api.mcp.dispatch.method_handler import MethodHandler
from bundlemcp.api.mcp.dispatch.method_registry import MethodRegistry
from bundlemcp.api.mcp.protocol.dialect import DialectRegistry
from bundlemcp.api.mcp.protocol.endpoint_context import EndpointContext
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.api.mcp.protocol.request_rejected import RequestRejected
from bundlemcp.api.mcp.protocol.session_header import SESSION_HEADER
from bundlemcp.api.mcp.routing.session_stream import SessionStream
from bundlemcp.application.contracts.live_state.session_store import SessionStore
from bundlemcp.application.contracts.live_state.signal_bus import SignalBus
from bundlemcp.domain.sessions.session_record import SessionRecord


def _method_not_allowed() -> Response:
    return Response(status_code=405, headers={"Allow": "POST"})


class SessionMcpAdapter:
    """Serves stateful (handshake/session) MCP requests."""

    def __init__(
        self,
        *,
        sessions: SessionStore,
        signals: SignalBus,
        dialects: DialectRegistry,
        initialize: MethodHandler[EndpointContext],
        methods: MethodRegistry,
        stream: SessionStream,
    ) -> None:
        self._sessions = sessions
        self._signals = signals
        self._dialects = dialects
        self._initialize = initialize
        self._methods = methods
        self._stream = stream

    async def handle_post(
        self, ctx: EndpointContext, message: JsonRpcMessage, endpoint_name: str
    ) -> Response:
        if message.method == "initialize":
            return await self._initialize.handle(ctx, message)

        try:
            request_ctx = await self._admit_session(ctx, endpoint_name)
        except RequestRejected as rejected:
            return rejected.response

        assert request_ctx.session is not None
        await self._sessions.touch(request_ctx.session.session_id)  # SES-1 (+ PROT-8)
        if message.is_response:
            # PROT-4: client reply to server->client request
            if message.id is not None:
                await self._signals.reply(str(message.id), message.body())
            return Response(status_code=202)

        return await self._methods.dispatch(request_ctx, message)

    async def open_stream(self, ctx: EndpointContext, endpoint_name: str) -> Response:
        """The server->client event stream of a handshake session (SSE)."""
        request_ctx = await self._admit_session(ctx, endpoint_name)
        return self._stream.open(request_ctx)

    async def close_session(self, request: Request, endpoint_name: str) -> Response:
        """Explicit session termination (handshake era only)."""
        session_id = request.headers.get(SESSION_HEADER, "")
        if not session_id:
            return _method_not_allowed()
        await self._sessions.delete(session_id)
        return Response(status_code=204)

    async def _admit_session(self, ctx: EndpointContext, endpoint_name: str) -> RequestContext:
        """Load the handshake session the request names, or reject the request."""
        session_id = ctx.request.headers.get(SESSION_HEADER, "")
        if not session_id:
            # PROT-13: neither era's opening — tell a dual-era client what to do.
            supported = self._dialects.modern_versions + self._dialects.handshake_versions
            raise RequestRejected(
                rpc_error(
                    None,
                    INVALID_PARAMS,
                    "params._meta must carry io.modelcontextprotocol/protocolVersion and "
                    "io.modelcontextprotocol/clientCapabilities, or the request must belong "
                    f"to a session opened with initialize; supported: {', '.join(supported)}",
                    status=400,
                    data={"supported": supported},
                )
            )
        # SES-2/SES-3: everything but initialize requires a live session record
        record = await self._sessions.load(session_id)
        dialect = self._dialects.handshake(record.protocol_version) if record else None
        if record is None or dialect is None or record.endpoint_name != endpoint_name:
            raise RequestRejected(JSONResponse({"error": "session not found"}, status_code=404))
        return self._session_context(ctx, record, dialect)

    @staticmethod
    def _session_context(
        ctx: EndpointContext, record: SessionRecord, dialect: Any
    ) -> RequestContext:
        return RequestContext(
            request=ctx.request,
            view=ctx.view,
            identity=ctx.identity,
            dialect=dialect,
            client_capabilities=record.client_capabilities,
            log_level=record.log_level,
            routing_key=record.session_id,
            session=record,
        )
