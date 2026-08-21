import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EndpointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    bundle_id: uuid.UUID
    profile: str
    auth_modes: list[str]
    rate_limit: dict[str, Any] | None
    enabled: bool
    created_at: datetime
    updated_at: datetime
