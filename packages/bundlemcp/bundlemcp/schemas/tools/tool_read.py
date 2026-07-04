import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ToolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    server_id: uuid.UUID
    name: str
    title: str | None
    description: str | None
    input_schema: dict[str, Any]
    annotations: dict[str, Any] | None
    last_seen_at: datetime
