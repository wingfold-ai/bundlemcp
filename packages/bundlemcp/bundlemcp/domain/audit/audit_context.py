import uuid

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.audit.audit_record import AuditRecord
from bundlemcp.domain.audit.audit_status import AuditStatus
from bundlemcp.domain.bundles.presented_tool import PresentedTool
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode


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
