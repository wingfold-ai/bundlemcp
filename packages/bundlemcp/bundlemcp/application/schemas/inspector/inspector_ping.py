from pydantic import BaseModel, Field


class InspectorPing(BaseModel):
    """A ping the target answered."""

    initialize_ms: int = Field(
        ge=0, description="Milliseconds connecting and initialising took, before the ping"
    )
    duration_ms: int = Field(ge=0, description="Milliseconds the ping itself took")
