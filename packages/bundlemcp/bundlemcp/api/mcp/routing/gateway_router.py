"""Front Controller for the Streamable-HTTP edge: admit caller, route by era."""

from fastapi import Request, Response

from bundlemcp.api.mcp.protocol.request_rejected import RequestRejected
from bundlemcp.api.mcp.protocol.session_header import SESSION_HEADER
from bundlemcp.api.mcp.routing.adapters.session_adapter import SessionMcpAdapter
from bundlemcp.api.mcp.routing.adapters.stateless_adapter import StatelessMcpAdapter
from bundlemcp.api.mcp.routing.admission_gate import AdmissionGate

# SEC-1: Upper bound on request body size before reading into memory (4 MB)
MAX_PAYLOAD_BYTES = 4 * 1024 * 1024


def _method_not_allowed() -> Response:
    # EP-1: the stateless era is POST-only; GET/DELETE exist for session clients.
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
        """Admit caller, validate payload, and dispatch to the matching era adapter."""
        if self._is_oversized(request):
            return Response(status_code=413, content="Payload Too Large")

        try:
            message = await self._admission.parse_envelope(request)
            ctx = await self._admission.admit_caller(request, endpoint_name)
        except RequestRejected as rejected:
            return rejected.response

        # PROT-13: the client's opening decides the era adapter, once per request.
        if message.has_modern_meta:
            return await self._stateless.handle_post(ctx, message, endpoint_name)
        return await self._session.handle_post(ctx, message, endpoint_name)

    async def close_session(self, request: Request, endpoint_name: str) -> Response:
        """Explicit session termination (session era only)."""
        if not request.headers.get(SESSION_HEADER):
            return _method_not_allowed()
        return await self._session.close_session(request, endpoint_name)

    async def open_stream(self, request: Request, endpoint_name: str) -> Response:
        """The server->client event stream of a session connection (SSE)."""
        if not request.headers.get(SESSION_HEADER):
            return _method_not_allowed()
        try:
            ctx = await self._admission.admit_caller(request, endpoint_name)
            return await self._session.open_stream(ctx, endpoint_name)
        except RequestRejected as rejected:
            return rejected.response

    @staticmethod
    def _is_oversized(request: Request) -> bool:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                return int(content_length) > MAX_PAYLOAD_BYTES
            except ValueError:
                pass
        return False
