"""Public MCP endpoints: POST/GET/DELETE /{endpoint_name}/mcp."""

from fastapi import Request, Response

from bundlemcp.api.http.controller import Controller
from bundlemcp.api.http.route import route
from bundlemcp.api.mcp.providers import McpEdgeProvider


class McpEndpointController(Controller):
    include_in_schema = False

    @route.post("/{endpoint_name}/mcp")
    async def post_message(
        self, endpoint_name: str, request: Request, edge: McpEdgeProvider
    ) -> Response:
        return await edge.post(request, endpoint_name)

    @route.get("/{endpoint_name}/mcp")
    async def open_stream(
        self, endpoint_name: str, request: Request, edge: McpEdgeProvider
    ) -> Response:
        return await edge.open_stream(request, endpoint_name)

    @route.delete("/{endpoint_name}/mcp")
    async def close_session(
        self, endpoint_name: str, request: Request, edge: McpEdgeProvider
    ) -> Response:
        return await edge.close_session(request, endpoint_name)
