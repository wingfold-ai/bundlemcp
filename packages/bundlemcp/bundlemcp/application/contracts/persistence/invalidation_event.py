from typing import Literal

from pydantic import BaseModel, Field

EntityType = Literal["server", "bundle", "bundle_tool", "endpoint", "api_key", "config"]


class InvalidationEvent(BaseModel):
    """Published after a config change so every replica drops its stale caches."""

    entity_type: EntityType = Field(description="Which kind of record changed")
    key: str = Field(description="Natural key of the changed record, or its id when it has no name")
    action: Literal["created", "updated", "deleted"] = Field(description="What happened to it")
