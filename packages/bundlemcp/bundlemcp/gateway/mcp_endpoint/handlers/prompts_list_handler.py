from typing import Any

from fastapi import Response

from bundlemcp.gateway.mcp_endpoint.handlers.member_fanout import MemberFanout
from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_result
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.mcp_endpoint.session_context import SessionContext
from bundlemcp.models import McpServer, PresentedName


class PromptsListHandler:
    """Every member's prompts, each name prefixed with its server."""

    def __init__(self, fanout: MemberFanout) -> None:
        self._fanout = fanout

    @staticmethod
    def _prefixed(server: McpServer, entry: dict[str, Any]) -> dict[str, Any]:
        entry["name"] = PresentedName(server=server.name, name=entry["name"]).text  # BND-8
        return entry

    async def handle(self, ctx: SessionContext, message: JsonRpcMessage) -> Response:
        prompts = await self._fanout.merged(
            ctx, lambda client: client.list_prompts(), key="name", present=self._prefixed
        )
        return rpc_result(message.id, {"prompts": prompts})
