import uuid
from datetime import datetime

from pydantic import Field

from bundlemcp.application.schemas.common.entity_read import EntityRead
from bundlemcp.domain.audit.audit_kind import AuditKind
from bundlemcp.domain.audit.audit_status import AuditStatus
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode


class AuditRecordRead(EntityRead):
    """One recorded tool call, successful or not, or one recorded management action."""

    id: uuid.UUID = Field(description="Identifier of the audit record")
    created_at: datetime = Field(description="When the call or action was recorded")
    kind: AuditKind = Field(
        description="What the record is about: tool_call for a call through an endpoint, "
        "management for an administrative action such as a secret-bearing export"
    )
    action: str | None = Field(
        description="What a management record says happened, such as "
        "'export.secrets_included'; null on a tool-call record. It never carries a value "
        "the action handled"
    )
    endpoint_id: uuid.UUID | None = Field(
        description="Endpoint the call arrived on; null once that endpoint is deleted"
    )
    endpoint_name: str = Field(
        description="Endpoint name as it was at the time of the call; empty on a management record"
    )
    bundle_name: str = Field(
        description="Bundle the endpoint exposed at the time of the call; empty on a management "
        "record"
    )
    server_name: str | None = Field(
        description="Upstream server the call was routed to; null if it never got that far"
    )
    tool_name: str | None = Field(description="Upstream tool name, without the bundle prefix")
    presented_tool_name: str | None = Field(
        description="Tool name as the client used it, including any override"
    )
    user_id: uuid.UUID | None = Field(description="Authenticated user, when OAuth was used")
    api_key_id: uuid.UUID | None = Field(description="API key used, when one was")
    auth_method: EndpointAuthMode | None = Field(
        description="How the caller authenticated: oauth, api_key or none"
    )
    session_id: str | None = Field(description="MCP session the call belonged to")
    idempotency_key: str | None = Field(
        description="The metering idempotency key the hook received for this invocation, the "
        "same on every leg; join the metering ledger on it. Null for a call denied before "
        "metering, such as an unknown tool"
    )
    status: AuditStatus = Field(
        description="Outcome: success, error, denied, or input_required when the call paused for "
        "the client's input and continues on its retry"
    )
    denied_reason: str | None = Field(
        description="Why a denied call was refused, such as a metering or rate-limit decision"
    )
    duration_ms: int | None = Field(
        description="Time spent on the upstream call; null when the call was denied"
    )
    error_message: str | None = Field(description="Failure detail when the call errored")
