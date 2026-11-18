import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from bundlemcp.domain.audit.audit_kind import AuditKind
from bundlemcp.domain.audit.audit_status import AuditStatus
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.shared.clock import utcnow


class AuditRecord(BaseModel):
    """Append-only record of a tool call or a management action.

    Nullable foreign keys and denormalized names let a record outlive the endpoint, user or
    key it names. A management record names no endpoint, bundle or tool; its ``action`` says
    what happened.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Identifier of the record")
    created_at: datetime = Field(
        default_factory=utcnow,
        description="When the call or action was recorded",
    )
    kind: AuditKind = Field(
        default=AuditKind.TOOL_CALL,
        description="What the record is about: a tool call, or a management action",
    )
    action: str | None = Field(
        default=None,
        description="What a management record says happened, such as "
        "'export.secrets_included'; null on a tool-call record",
    )
    endpoint_id: uuid.UUID | None = Field(
        default=None,
        description="Endpoint the call arrived on; cleared if that endpoint is later deleted",
    )
    endpoint_name: str = Field(
        description="Endpoint name as it was at the time, kept so the record survives a delete; "
        "empty on a management record"
    )
    bundle_name: str = Field(
        description="Bundle the endpoint exposed at the time of the call; empty on a management "
        "record"
    )
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

    @classmethod
    def management_event(
        cls,
        action: str,
        *,
        user_id: uuid.UUID | None,
        api_key_id: uuid.UUID | None,
        auth_method: EndpointAuthMode | None,
    ) -> AuditRecord:
        """A successful management action by the given user or key; it names no endpoint or tool.

        Only the action's name is kept, never a value the action handled.
        """
        return cls(
            kind=AuditKind.MANAGEMENT,
            action=action,
            endpoint_name="",
            bundle_name="",
            user_id=user_id,
            api_key_id=api_key_id,
            auth_method=auth_method,
            status=AuditStatus.SUCCESS,
        )
