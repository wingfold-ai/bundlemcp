"""The Streamable-HTTP edge: admit the caller, pick the client's dialect, hand the message on.

Implemented directly rather than through FastMCP's server session manager so
that session state lives in Valkey and any replica serves any request. FastMCP
is used for the upstream side only. One endpoint serves every supported MCP
revision: a modern-era request is self-describing and served statelessly, a
handshake-era request is served through the session it opened with
``initialize``.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Mapping
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from mcp.shared.inbound import (
    ERROR_CODE_HTTP_STATUS,
    InboundLadderRejection,
    classify_inbound_request,
)
from mcp.types import INVALID_PARAMS, INVALID_REQUEST, LOG_LEVEL_META_KEY, PARSE_ERROR
from pydantic import ValidationError

from bundlemcp.gateway.composition import load_bundle_view
from bundlemcp.gateway.dialect import DialectRegistry
from bundlemcp.gateway.mcp_endpoint.authentication import (
    EndpointAuthentication,
    unauthorized_challenge,
)
from bundlemcp.gateway.mcp_endpoint.endpoint_context import EndpointContext
from bundlemcp.gateway.mcp_endpoint.handlers import SESSION_HEADER
from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_error
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.mcp_endpoint.log_levels import LOG_LEVELS
from bundlemcp.gateway.mcp_endpoint.method_handler import MethodHandler
from bundlemcp.gateway.mcp_endpoint.method_registry import MethodRegistry
from bundlemcp.gateway.mcp_endpoint.request_context import RequestContext
from bundlemcp.gateway.mcp_endpoint.request_rejected import RequestRejected
from bundlemcp.gateway.mcp_endpoint.sse import (
    KEEPALIVE_SECONDS,
    SSE_HEADERS,
    SSE_KEEPALIVE,
    sse_data,
)
from bundlemcp.gateway.ratelimit import AuthFailureGuard
from bundlemcp.gateway.signals import SignalBus
from bundlemcp.gateway.streams import STREAM_CLOSING, StreamKey, StreamRegistry
from bundlemcp.store import UnitOfWorkFactory
from bundlemcp.store.sessions import SessionRecord, SessionStore


def _carries_credential(request: Request) -> bool:
    return "authorization" in request.headers or "x-api-key" in request.headers


def _method_not_allowed() -> Response:
    # EP-1: the modern era is POST-only; GET/DELETE exist for handshake sessions.
    return Response(status_code=405, headers={"Allow": "POST"})


class McpEdge:
    """Serves POST, GET and DELETE on ``/{endpoint}/mcp`` for every endpoint."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        sessions: SessionStore,
        registry: StreamRegistry,
        signals: SignalBus,
        authentication: EndpointAuthentication,
        auth_failures: AuthFailureGuard,
        dialects: DialectRegistry,
        initialize: MethodHandler[EndpointContext],
        methods: MethodRegistry,
        public_base: str,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._sessions = sessions
        self._registry = registry
        self._signals = signals
        self._authentication = authentication
        self._auth_failures = auth_failures
        self._dialects = dialects
        self._initialize = initialize
        self._methods = methods
        self._public_base = public_base

    async def post(self, request: Request, endpoint_name: str) -> Response:
        try:
            ctx = await self._admit(request, endpoint_name)
            message = await self._parse(request)
            # PROT-13: the client's opening decides the dialect, once per request.
            if message.has_modern_meta:
                request_ctx = self._admit_modern(ctx, message)
            elif message.method == "initialize":
                return await self._initialize.handle(ctx, message)
            else:
                request_ctx = await self._admit_session(ctx, endpoint_name)
        except RequestRejected as rejected:
            return rejected.response

        if request_ctx.session is not None:
            await self._sessions.touch(request_ctx.session.session_id)  # SES-1 (+ PROT-8)
            if message.is_response:
                # PROT-4: the client's reply to a server->client request — route
                # it to the awaiting call.
                if message.id is not None:
                    await self._signals.reply(str(message.id), message.body())
                return Response(status_code=202)
        elif message.is_response:
            return rpc_error(
                None,
                INVALID_REQUEST,
                "a modern-era client sends requests and notifications only",
                status=400,
            )
        return await self._methods.dispatch(request_ctx, message)

    async def close_session(self, request: Request, endpoint_name: str) -> Response:
        """Explicit session termination (handshake era only)."""
        session_id = request.headers.get(SESSION_HEADER, "")
        if not session_id:
            return _method_not_allowed()
        await self._sessions.delete(session_id)
        return Response(status_code=204)

    async def open_stream(self, request: Request, endpoint_name: str) -> Response:
        """The server->client event stream of a handshake session (SSE).

        Carries list_changed notifications and server->client requests. The open
        stream is replica-pinned; messages from other replicas arrive via the
        signal bus. Modern clients open the equivalent with subscriptions/listen.
        """
        if not request.headers.get(SESSION_HEADER):
            return _method_not_allowed()
        try:
            ctx = await self._admit(request, endpoint_name)
            request_ctx = await self._admit_session(ctx, endpoint_name)
        except RequestRejected as rejected:
            return rejected.response
        key = StreamKey(
            endpoint_name=request_ctx.view.endpoint.name,
            bundle_name=request_ctx.view.bundle.name,
            stream_id=request_ctx.routing_key,
        )
        queue = self._registry.register_stream(key)
        return StreamingResponse(
            self._events(key, queue), media_type="text/event-stream", headers=SSE_HEADERS
        )

    async def _events(self, key: StreamKey, queue: asyncio.Queue) -> AsyncIterator[str]:
        try:
            yield ": connected\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                except TimeoutError:
                    yield SSE_KEEPALIVE
                    await self._sessions.touch(key.stream_id)  # stream open = active
                    continue
                if payload is STREAM_CLOSING:
                    return
                yield sse_data(payload)
        finally:
            self._registry.unregister_stream(key, queue)

    async def _admit(self, request: Request, endpoint_name: str) -> EndpointContext:
        """Resolve the endpoint and authenticate the caller, or reject the request."""
        async with self._unit_of_work_factory.open() as uow:
            view = await load_bundle_view(uow.session, endpoint_name)
            if view is None:
                raise RequestRejected(JSONResponse({"error": "not found"}, status_code=404))
            if _carries_credential(request):
                locked = await self._auth_failures.rejection_if_locked(request)  # RATE-5
                if locked is not None:
                    raise RequestRejected(locked)
            identity = await self._authentication.authenticate(request, uow, view)
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

    def _admit_modern(self, ctx: EndpointContext, message: JsonRpcMessage) -> RequestContext:
        """Validate the per-request envelope and mirrored headers (PROT-13, PROT-15)."""
        route = classify_inbound_request(
            message.body(),
            headers=_lowercase(ctx.request.headers),
            supported_modern_versions=self._dialects.modern_versions,
        )
        if isinstance(route, InboundLadderRejection):
            raise RequestRejected(_rejection(message, route.code, route.message, route.data))
        dialect = self._dialects.modern(route.protocol_version)
        if dialect is None:  # pragma: no cover - the ladder already checked the version
            raise RequestRejected(
                _rejection(message, INVALID_PARAMS, "unsupported protocol version", None)
            )
        log_level = message.meta.get(LOG_LEVEL_META_KEY)
        if log_level is not None and log_level not in LOG_LEVELS:  # PROT-20
            raise RequestRejected(
                _rejection(message, INVALID_PARAMS, f"unknown log level {log_level!r}", None)
            )
        capabilities = route.client_capabilities
        return RequestContext(
            request=ctx.request,
            view=ctx.view,
            identity=ctx.identity,
            dialect=dialect,
            client_capabilities=dict(capabilities) if isinstance(capabilities, Mapping) else {},
            log_level=log_level,
            routing_key=uuid.uuid4().hex,  # SES-15: no session, a per-request key
            session=None,
        )

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


def _lowercase(headers: Mapping[str, str]) -> dict[str, str]:
    return {name.lower(): value for name, value in headers.items()}


def _rejection(
    message: JsonRpcMessage, code: int, text: str, data: dict[str, Any] | None
) -> Response:
    return rpc_error(
        message.id, code, text, status=ERROR_CODE_HTTP_STATUS.get(code, 400), data=data
    )
