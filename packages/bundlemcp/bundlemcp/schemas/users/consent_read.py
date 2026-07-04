import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConsentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: str
    endpoint_id: uuid.UUID
    granted_at: datetime
