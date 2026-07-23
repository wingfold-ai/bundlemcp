"""Public MCP endpoints: POST/GET/DELETE /{endpoint_name}/mcp.

The Streamable-HTTP edge is implemented directly (not via FastMCP's server
session manager) so that session state lives in the RESP store and any replica
serves any request. FastMCP is used for the upstream side. The route handlers
and helpers live in ``edge.py``; the wiring holder and the internal call-outcome
value object have their own modules.
"""

from bundlemcp.gateway.mcp_endpoint._call_outcome import _CallOutcome
from bundlemcp.gateway.mcp_endpoint.edge import router
from bundlemcp.gateway.mcp_endpoint.gateway_runtime import GatewayRuntime

__all__ = ["GatewayRuntime", "_CallOutcome", "router"]
