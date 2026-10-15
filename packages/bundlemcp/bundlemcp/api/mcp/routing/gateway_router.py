"""Front Controller for the Streamable-HTTP edge: admit caller, route by era."""

from fastapi import Request, Response

from bundlemcp.api.mcp.protocol.request_rejected import RequestRejected
from bundlemcp.api.mcp.protocol.session_header import SESSION_HEADER
from bundlemcp.api.mcp.routing.adapters.session_adapter import SessionMcpAdapter
from bundlemcp.api.mcp.routing.adapters.stateless_adapter import StatelessMcpAdapter
from bundlemcp.api.mcp.routing.admission_gate import AdmissionGate


def _method_not_allowed() -> Response:
    # the stateless era is POST-only; GET/DELETE exist for session clients.
    return Response(status_code=405, headers={"Allow": "POST"})


class McpGatewayRouter:
    """Front Controller serving POST, GET and DELETE on ``/{endpoint}/mcp``."""

    def __init__(
        self,
        *,
        admission: AdmissionGate,
        stateless_adapter: StatelessMcpAdapter,
        session_adapter: SessionMcpAdapter,
    ) -> None:
        self._admission = admission
        self._stateless = stateless_adapter
        self._session = session_adapter

    async def post(self, request: Request, endpoint_name: str) -> Response:
        """Admit caller, validate payload, and dispatch to the matching era adapter.

        The body size is already bounded by the request body limit middleware.
        """
        try:
            message = await self._admission.parse_envelope(request)
            ctx = await self._admission.admit_caller(request, endpoint_name)
        except RequestRejected as rejected:
            return rejected.answer

        # the client's opening decides the era adapter, once per request.
        if message.has_modern_meta:
            response = await self._stateless.handle_post(ctx, message, endpoint_name)
        else:
            response = await self._session.handle_post(ctx, message, endpoint_name)
        return ctx.cors.apply(response)

    async def preflight(self, request: Request, endpoint_name: str) -> Response:
        """A browser's CORS preflight, answered from the endpoint's allowed origins."""
        return await self._admission.preflight(request, endpoint_name)

    async def close_session(self, request: Request, endpoint_name: str) -> Response:
        """Explicit session termination (session era only)."""
        if not request.headers.get(SESSION_HEADER):
            return _method_not_allowed()
        try:
            ctx = await self._admission.admit_caller(request, endpoint_name)
        except RequestRejected as rejected:
            return rejected.answer
        return ctx.cors.apply(await self._session.close_session(ctx, endpoint_name))

    async def open_stream(self, request: Request, endpoint_name: str) -> Response:
        """The server->client event stream of a session connection (SSE)."""
        if not request.headers.get(SESSION_HEADER):
            return _method_not_allowed()
        try:
            ctx = await self._admission.admit_caller(request, endpoint_name)
            return ctx.cors.apply(await self._session.open_stream(ctx, endpoint_name))
        except RequestRejected as rejected:
            return rejected.answer
