"""Opening a handshake-era session: negotiate the revision and advertise the bundle."""

from fastapi import Response
from mcp.types import INVALID_PARAMS

from bundlemcp.gateway.composition import aggregate_capabilities
from bundlemcp.gateway.dialect import DialectRegistry
from bundlemcp.gateway.mcp_endpoint.endpoint_context import EndpointContext
from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_error, rpc_result
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.mcp_endpoint.server_info import server_info
from bundlemcp.store.sessions import SessionRecord, SessionStore

SESSION_HEADER = "mcp-session-id"


class InitializeHandler:
    def __init__(self, sessions: SessionStore, dialects: DialectRegistry) -> None:
        self._sessions = sessions
        self._dialects = dialects

    async def handle(self, ctx: EndpointContext, message: JsonRpcMessage) -> Response:
        requested = message.params.get("protocolVersion")
        dialect = self._dialects.negotiate_handshake(requested)  # PROT-12
        if dialect is None:
            return rpc_error(message.id, INVALID_PARAMS, self._unsupported(requested))
        record = SessionRecord(
            session_id=SessionStore.new_session_id(),
            endpoint_name=ctx.view.endpoint.name,
            bundle_name=ctx.view.bundle.name,
            identity=ctx.identity,
            protocol_version=dialect.version,
            client_capabilities=message.param("capabilities", {}),
        )
        await self._sessions.create(record)  # SES-1
        result = {
            "protocolVersion": dialect.version,
            "capabilities": aggregate_capabilities(ctx.view),  # PROT-11
            "serverInfo": server_info(ctx.view.bundle.name),
        }
        if ctx.view.bundle.description:
            result["instructions"] = ctx.view.bundle.description
        response = rpc_result(message.id, result)
        response.headers[SESSION_HEADER] = record.session_id
        return response

    def _unsupported(self, requested: object) -> str:
        """Name what the gateway does speak: a handshake client has no other way to learn it."""
        handshake = self._dialects.handshake_versions
        if handshake:
            return f"unsupported protocolVersion {requested!r}; supported: {', '.join(handshake)}"
        return (
            "the initialize handshake is not served by this gateway; send every request with "
            "io.modelcontextprotocol/protocolVersion in params._meta; supported: "
            + ", ".join(self._dialects.modern_versions)
        )
