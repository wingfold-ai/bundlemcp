"""Opening a handshake-era session: negotiate the revision and advertise the bundle."""

from fastapi import Response
from mcp.types import INVALID_PARAMS

from bundlemcp.api.mcp.protocol.dialect import DialectRegistry
from bundlemcp.api.mcp.protocol.endpoint_context import EndpointContext
from bundlemcp.api.mcp.protocol.jsonrpc import rpc_error, rpc_result
from bundlemcp.api.mcp.protocol.jsonrpc_message import JsonRpcMessage
from bundlemcp.api.mcp.protocol.server_info import server_info
from bundlemcp.api.mcp.protocol.session_header import SESSION_HEADER
from bundlemcp.application.contracts.live_state.session_store import SessionStore
from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.domain.bundles.bundle_capabilities import aggregate_capabilities
from bundlemcp.domain.sessions.session_id import new_session_id
from bundlemcp.domain.sessions.session_record import SessionRecord


class InitializeHandler:
    def __init__(
        self,
        sessions: SessionStore,
        dialects: DialectRegistry,
        runtime_config: RuntimeConfig,
        *,
        member_notifications: bool,
    ) -> None:
        # member_notifications: whether members' list changes and resource
        # updates reach clients, which decides whether they are advertised
        self._sessions = sessions
        self._dialects = dialects
        self._runtime_config = runtime_config
        self._member_notifications = member_notifications

    async def handle(self, ctx: EndpointContext, message: JsonRpcMessage) -> Response:
        requested = message.params.get("protocolVersion")
        dialect = self._dialects.negotiate_handshake(requested)
        if dialect is None:
            return rpc_error(message.id, INVALID_PARAMS, self._unsupported(requested))
        record = SessionRecord(
            session_id=new_session_id(),
            endpoint_name=ctx.view.endpoint.name,
            bundle_name=ctx.view.bundle.name,
            identity=ctx.identity,
            protocol_version=dialect.version,
            client_capabilities=message.param("capabilities", {}),
        )
        await self._sessions.create(record, await self._runtime_config.session_lifetime())
        result = {
            "protocolVersion": dialect.version,
            "capabilities": aggregate_capabilities(
                ctx.view, member_notifications=self._member_notifications
            ).model_dump(),
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
