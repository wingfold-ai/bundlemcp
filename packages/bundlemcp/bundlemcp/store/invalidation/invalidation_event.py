from typing import Literal

from pydantic import BaseModel

from bundlemcp.store.invalidation._common import EntityType


class InvalidationEvent(BaseModel):
    entity_type: EntityType
    key: str  # natural key or str(uuid)
    action: Literal["created", "updated", "deleted"]
