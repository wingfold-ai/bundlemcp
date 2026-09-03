from typing import Any

from fastapi import Response

from bundlemcp.gateway.composition import PresentedTool
from bundlemcp.gateway.mcp_endpoint.jsonrpc import rpc_result
from bundlemcp.gateway.mcp_endpoint.jsonrpc_message import JsonRpcMessage
from bundlemcp.gateway.mcp_endpoint.session_context import SessionContext


class ToolsListHandler:
    """The curated, prefixed tool surface of the endpoint's bundle."""

    @staticmethod
    def _entry(tool: PresentedTool) -> dict[str, Any]:
        entry: dict[str, Any] = {"name": tool.presented_name, "inputSchema": tool.input_schema}
        if tool.title:
            entry["title"] = tool.title
        if tool.description:
            entry["description"] = tool.description
        if tool.annotations:
            entry["annotations"] = tool.annotations
        return entry

    async def handle(self, ctx: SessionContext, message: JsonRpcMessage) -> Response:
        return rpc_result(message.id, {"tools": [self._entry(t) for t in ctx.view.tools]})
