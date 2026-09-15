"""FastAPI providers for gateway-owned collaborators, each read off the app's container."""

from typing import Annotated

from fastapi import Depends, Request

from bundlemcp.api.mcp.routing.gateway_router import McpGatewayRouter


def get_mcp_router(request: Request) -> McpGatewayRouter:
    return request.app.state.container.mcp_router


McpGatewayRouterProvider = Annotated[McpGatewayRouter, Depends(get_mcp_router)]
