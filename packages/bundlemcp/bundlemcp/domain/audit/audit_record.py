import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from bundlemcp.domain.audit.audit_status import AuditStatus
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.shared.clock import utcnow


class AuditRecord(BaseModel):
    """Append-only per-tool-call record; nullable FKs + denormalized names survive deletes."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Identifier of the record")
    created_at: datetime = Field(
        default_factory=utcnow,
        description="When the call was recorded",
    )
    endpoint_id: uuid.UUID | None = Field(
        default=None,
        description="Endpoint the call arrived on; cleared if that endpoint is later deleted",
    )
    endpoint_name: str = Field(
        description="Endpoint name as it was at the time, kept so the record survives a delete"
    )
    bundle_name: str = Field(description="Bundle the endpoint exposed at the time of the call")
    server_name: str | None = Field(
        default=None,
        description="Upstream server the call was routed to; null if it never got that far",
    )
    tool_name: str | None = Field(
        default=None, description="Tool name as the upstream server knows it"
    )
    presented_tool_name: str | None = Field(
        default=None,
        description="Tool name as the client used it, after prefixing, overrides and the profile",
    )
    user_id: uuid.UUID | None = Field(
        default=None,
        description="Authenticated user, when OAuth was used",
    )
    api_key_id: uuid.UUID | None = Field(
        default=None,
        description="API key used, when one was",
    )
    auth_method: EndpointAuthMode | None = Field(
        default=None,
        description="How the caller authenticated: oauth, api_key or none",
    )
    session_id: str | None = Field(default=None, description="MCP session the call belonged to")
    idempotency_key: str | None = Field(
        default=None,
        description="Metering idempotency key of the invocation this leg belongs to, the same "
        "on all its legs; null for a call denied before metering, such as an unknown tool",
    )
    status: AuditStatus = Field(description="Outcome of the call: success, error or denied")
    denied_reason: str | None = Field(
        default=None,
        description="Why a denied call was refused, such as a metering or rate-limit decision",
    )
    duration_ms: int | None = Field(
        default=None,
        description="Time spent on the upstream call; null when the call was denied",
    )
    error_message: str | None = Field(
        default=None, description="Failure detail when the call errored, truncated if long"
    )
