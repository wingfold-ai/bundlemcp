from pydantic import Field

from bundlemcp.gateway.mcp_endpoint.endpoint_context import EndpointContext
from bundlemcp.store.sessions import SessionRecord


class SessionContext(EndpointContext):
    """An admitted request that also belongs to a live MCP session."""

    session: SessionRecord = Field(description="The session the client opened with initialize")
