import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AuditRecordRead(BaseModel):
    """One recorded tool call, successful or not."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Identifier of the audit record")
    created_at: datetime = Field(description="When the call was recorded")
    endpoint_id: uuid.UUID | None = Field(
        description="Endpoint the call arrived on; null once that endpoint is deleted"
    )
    endpoint_name: str = Field(description="Endpoint name as it was at the time of the call")
    bundle_name: str = Field(description="Bundle the endpoint exposed at the time of the call")
    server_name: str | None = Field(
        description="Upstream server the call was routed to; null if it never got that far"
    )
    tool_name: str | None = Field(description="Upstream tool name, without the bundle prefix")
    presented_tool_name: str | None = Field(
        description="Tool name as the client used it, including any override"
    )
    user_id: uuid.UUID | None = Field(description="Authenticated user, when OAuth was used")
    api_key_id: uuid.UUID | None = Field(description="API key used, when one was")
    auth_method: str | None = Field(
        description="How the caller authenticated: oauth, api_key or none"
    )
    session_id: str | None = Field(description="MCP session the call belonged to")
    status: str = Field(description="Outcome: success, error or denied")
    denied_reason: str | None = Field(
        description="Why a denied call was refused, such as a metering or rate-limit decision"
    )
    duration_ms: int | None = Field(
        description="Time spent on the upstream call; null when the call was denied"
    )
    error_message: str | None = Field(description="Failure detail when the call errored")
