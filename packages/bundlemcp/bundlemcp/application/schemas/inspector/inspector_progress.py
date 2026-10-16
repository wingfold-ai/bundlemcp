from typing import Literal

from pydantic import BaseModel, Field


class InspectorProgress(BaseModel):
    """A progress notification the target sent during a call; the 'progress' stream event."""

    type: Literal["progress"] = Field(
        default="progress", description="Names the stream event this payload is"
    )
    progress: float = Field(description="Progress so far, in the target's own units")
    total: float | None = Field(default=None, description="The total, when the target knows it")
    message: str | None = Field(default=None, description="What the target is doing now")
    elapsed_ms: int = Field(ge=0, description="Milliseconds since the call was sent")
