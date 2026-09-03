from fastapi import Response

from bundlemcp.gateway.mcp_endpoint.handlers.member_fanout import MemberFanout
from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_result
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.mcp_endpoint.session_context import SessionContext


class ResourceTemplatesListHandler:
    """Every member's resource templates, de-duplicated by URI template."""

    def __init__(self, fanout: MemberFanout) -> None:
        self._fanout = fanout

    async def handle(self, ctx: SessionContext, message: JsonRpcMessage) -> Response:
        items = await self._fanout.merged(
            ctx, lambda client: client.list_resource_templates(), key="uriTemplate"
        )
        return rpc_result(message.id, {"resourceTemplates": items})
