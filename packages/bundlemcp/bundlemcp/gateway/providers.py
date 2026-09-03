"""FastAPI providers for gateway-owned collaborators, each read off the app's container."""

from typing import Annotated

from fastapi import Depends, Request

from bundlemcp.gateway.mcp_endpoint.mcp_edge import McpEdge


def get_mcp_edge(request: Request) -> McpEdge:
    return request.app.state.container.mcp_edge


McpEdgeProvider = Annotated[McpEdge, Depends(get_mcp_edge)]
