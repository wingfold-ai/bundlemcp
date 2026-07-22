import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    key_prefix: str
    kind: str
    endpoint_ids: list[str]
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime
