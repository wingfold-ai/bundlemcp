import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AuditCursor(BaseModel):
    """Where a newest-first walk through the audit log stopped: the last record it returned."""

    model_config = ConfigDict(frozen=True)

    created_at: datetime = Field(description="Creation time of the last record returned")
    id: uuid.UUID = Field(description="Id of the last record returned, which breaks time ties")
