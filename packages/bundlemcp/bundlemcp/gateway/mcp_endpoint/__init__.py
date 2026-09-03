"""Public MCP endpoints: POST/GET/DELETE /{endpoint_name}/mcp.

The Streamable-HTTP edge is implemented directly (not via FastMCP's server
session manager) so that session state lives in the RESP store and any replica
serves any request. FastMCP is used for the upstream side.

``edge.py`` owns the HTTP surface and the JSON-RPC method dispatch; each method
is handled by a module beside it — ``tool_call`` for tools/call, ``passthrough``
for the read-only prompt and resource methods, with ``authentication``,
``rate_limit``, ``forwarded_headers``, ``relay_handlers`` and
``upstream_driver`` behind them.
"""

from bundlemcp.gateway.mcp_endpoint.edge import router
from bundlemcp.gateway.mcp_endpoint.gateway_runtime import GatewayRuntime

__all__ = ["GatewayRuntime", "router"]
