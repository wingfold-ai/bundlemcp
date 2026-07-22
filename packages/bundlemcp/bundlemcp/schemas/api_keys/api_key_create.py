import uuid
from typing import Literal

from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    name: str
    kind: Literal["endpoint", "service"] = "endpoint"
    endpoint_ids: list[uuid.UUID] = Field(default_factory=list)
