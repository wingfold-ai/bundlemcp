import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    endpoint_id: uuid.UUID | None
    endpoint_name: str
    bundle_name: str
    server_name: str | None
    tool_name: str | None
    presented_tool_name: str | None
    user_id: uuid.UUID | None
    api_key_id: uuid.UUID | None
    auth_method: str | None
    session_id: str | None
    status: str
    denied_reason: str | None
    duration_ms: int | None
    error_message: str | None
