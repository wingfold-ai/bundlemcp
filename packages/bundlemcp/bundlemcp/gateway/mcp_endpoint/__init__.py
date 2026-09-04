"""Public MCP endpoints: POST/GET/DELETE /{endpoint_name}/mcp.

The Streamable-HTTP edge is implemented directly (not via FastMCP's server
session manager) so that session state lives in the RESP store and any replica
serves any request. FastMCP is used for the upstream side.

``McpEdge`` owns the HTTP surface; each JSON-RPC method is a handler class
looked up in a ``MethodRegistry``, with ``authentication``, ``tool_call`` and
``handlers`` behind them. ``McpEdgeAssembly`` is how the composition root
builds one.
"""

from bundlemcp.gateway.mcp_endpoint.mcp_edge import McpEdge
from bundlemcp.gateway.mcp_endpoint.mcp_edge_assembly import McpEdgeAssembly
from bundlemcp.gateway.mcp_endpoint.mcp_endpoint_controller import McpEndpointController

__all__ = ["McpEdge", "McpEdgeAssembly", "McpEndpointController"]
