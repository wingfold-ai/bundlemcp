import uuid

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.gateway.composition import PresentedTool
from bundlemcp.gateway.mcp_endpoint.request_context import RequestContext
from bundlemcp.models import AuditRecord, AuditStatus, EndpointAuthMode


class AuditContext(BaseModel):
    """Everything an audit record says about a call, apart from how it ended."""

    model_config = ConfigDict(frozen=True)

    endpoint_id: uuid.UUID = Field(description="Endpoint the call arrived on")
    endpoint_name: str = Field(description="Endpoint name at the time of the call")
    bundle_name: str = Field(description="Bundle the endpoint exposed")
    presented_tool_name: str = Field(description="Tool name as the client used it")
    user_id: uuid.UUID | None = Field(description="Authenticated user, when OAuth was used")
    api_key_id: uuid.UUID | None = Field(description="API key used, when one was")
    auth_method: EndpointAuthMode = Field(description="How the caller authenticated")
    session_id: str = Field(
        description="Routing key of the call: the MCP session for a handshake client, the "
        "request id for a modern one"
    )
    server_name: str | None = Field(default=None, description="Upstream server, once resolved")
    tool_name: str | None = Field(default=None, description="Upstream tool name, once resolved")

    @classmethod
    def for_request(cls, ctx: RequestContext, presented_tool_name: str) -> "AuditContext":
        return cls(
            endpoint_id=ctx.view.endpoint.id,
            endpoint_name=ctx.view.endpoint.name,
            bundle_name=ctx.view.bundle.name,
            presented_tool_name=presented_tool_name,
            user_id=ctx.identity.user_uuid,
            api_key_id=ctx.identity.api_key_uuid,
            auth_method=ctx.identity.auth_method,
            session_id=ctx.routing_key,
        )

    def resolved(self, tool: PresentedTool) -> "AuditContext":
        return self.model_copy(
            update={"server_name": tool.server.name, "tool_name": tool.tool.name}
        )

    def record(
        self,
        status: AuditStatus,
        *,
        denied_reason: str | None = None,
        error_message: str | None = None,
        duration_ms: int | None = None,
    ) -> AuditRecord:
        return AuditRecord(
            status=status,
            denied_reason=denied_reason,
            error_message=error_message,
            duration_ms=duration_ms,
            **self.model_dump(),
        )
