import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EndpointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    bundle_id: uuid.UUID
    profile: str
    auth_modes: list[str]
    enabled: bool
    created_at: datetime
    updated_at: datetime
