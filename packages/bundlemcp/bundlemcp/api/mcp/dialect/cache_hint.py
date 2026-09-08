from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CacheHint(BaseModel):
    """How long a client may keep a list or read result, and who may share it."""

    model_config = ConfigDict(frozen=True)

    ttl_ms: int = Field(ge=0, description="Milliseconds the result stays fresh; 0 means stale now")
    scope: Literal["public", "private"] = Field(
        description="'public' when the result is the same for every caller and shared caches "
        "may serve it; 'private' when it depends on the caller"
    )
