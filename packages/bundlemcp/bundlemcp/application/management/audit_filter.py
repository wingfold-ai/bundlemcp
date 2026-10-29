import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from bundlemcp.domain.audit.audit_kind import AuditKind
from bundlemcp.domain.audit.audit_record import AuditRecord
from bundlemcp.domain.audit.audit_status import AuditStatus


class AuditFilter(BaseModel):
    """The narrowing a listing of audit records may ask for; every field is optional."""

    created_from: datetime | None = Field(default=None, description="Earliest call time included")
    created_to: datetime | None = Field(default=None, description="Latest call time included")
    kind: AuditKind | None = Field(
        default=None,
        description="Only records of this kind: tool_call for tool calls, management for "
        "management actions",
    )
    endpoint_name: str | None = Field(default=None, description="Only calls on this endpoint")
    bundle_name: str | None = Field(default=None, description="Only calls into this bundle")
    server_name: str | None = Field(default=None, description="Only calls routed to this server")
    tool_name: str | None = Field(
        default=None,
        description="Only calls of this tool, matched by upstream or client-visible name",
    )
    user_id: uuid.UUID | None = Field(default=None, description="Only calls by this user")
    api_key_id: uuid.UUID | None = Field(default=None, description="Only calls with this key")
    status: AuditStatus | None = Field(default=None, description="Only calls with this outcome")
    idempotency_key: str | None = Field(
        default=None,
        description="Only the legs of the invocation with this metering idempotency key",
    )

    def matches(self, record: AuditRecord) -> bool:
        """Whether a record passes every narrowing this filter sets.

        The time range includes both ends, the tool narrowing matches either the upstream or
        the client-visible tool name, and every other field must equal the record's.
        """
        return (
            (self.created_from is None or record.created_at >= self.created_from)
            and (self.created_to is None or record.created_at <= self.created_to)
            and (self.kind is None or record.kind == self.kind)
            and (self.endpoint_name is None or record.endpoint_name == self.endpoint_name)
            and (self.bundle_name is None or record.bundle_name == self.bundle_name)
            and (self.server_name is None or record.server_name == self.server_name)
            and (
                self.tool_name is None
                or self.tool_name in (record.tool_name, record.presented_tool_name)
            )
            and (self.user_id is None or record.user_id == self.user_id)
            and (self.api_key_id is None or record.api_key_id == self.api_key_id)
            and (self.status is None or record.status == self.status)
            and (self.idempotency_key is None or record.idempotency_key == self.idempotency_key)
        )
