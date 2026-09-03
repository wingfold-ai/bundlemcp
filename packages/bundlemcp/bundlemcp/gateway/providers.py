"""FastAPI providers for gateway-owned collaborators, each read off the app's container."""

from typing import Annotated

from fastapi import Depends, Request

from bundlemcp.gateway.mcp_endpoint.gateway_runtime import GatewayRuntime


def get_gateway_runtime(request: Request) -> GatewayRuntime:
    return request.app.state.container.gateway


GatewayRuntimeProvider = Annotated[GatewayRuntime, Depends(get_gateway_runtime)]
