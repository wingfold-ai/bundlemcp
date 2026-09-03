"""Opening a session: negotiate the protocol version and advertise the bundle."""

from fastapi import Response

from bundlemcp.gateway.composition import aggregate_capabilities
from bundlemcp.gateway.mcp_endpoint.endpoint_context import EndpointContext
from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_error, rpc_result
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.protocol_version import SUPPORTED_PROTOCOL_VERSIONS, negotiate_version
from bundlemcp.store.sessions import SessionRecord, SessionStore

SESSION_HEADER = "mcp-session-id"
SERVER_VERSION = "0.1.0"


class InitializeHandler:
    def __init__(self, sessions: SessionStore) -> None:
        self._sessions = sessions

    async def handle(self, ctx: EndpointContext, message: JsonRpcMessage) -> Response:
        requested = message.params.get("protocolVersion")
        negotiated = negotiate_version(requested)  # PROT-12
        if negotiated is None:
            return rpc_error(
                message.id,
                -32602,
                f"unsupported protocolVersion {requested!r}; "
                f"supported: {', '.join(SUPPORTED_PROTOCOL_VERSIONS)}",
            )
        record = SessionRecord(
            session_id=SessionStore.new_session_id(),
            endpoint_name=ctx.view.endpoint.name,
            bundle_name=ctx.view.bundle.name,
            identity=ctx.identity,
            protocol_version=negotiated,
            client_capabilities=message.param("capabilities", {}),
        )
        await self._sessions.create(record)  # SES-1
        result = {
            "protocolVersion": negotiated,
            "capabilities": aggregate_capabilities(ctx.view),  # PROT-11
            "serverInfo": {"name": f"bundlemcp/{ctx.view.bundle.name}", "version": SERVER_VERSION},
        }
        if ctx.view.bundle.description:
            result["instructions"] = ctx.view.bundle.description
        response = rpc_result(message.id, result)
        response.headers[SESSION_HEADER] = record.session_id
        return response
