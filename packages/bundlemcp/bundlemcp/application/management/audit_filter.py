import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from bundlemcp.domain.audit.audit_status import AuditStatus


class AuditFilter(BaseModel):
    """The narrowing a listing of audit records may ask for; every field is optional."""

    created_from: datetime | None = Field(default=None, description="Earliest call time included")
    created_to: datetime | None = Field(default=None, description="Latest call time included")
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
