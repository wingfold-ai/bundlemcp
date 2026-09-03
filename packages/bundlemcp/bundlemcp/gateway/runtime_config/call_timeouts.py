from pydantic import BaseModel, ConfigDict, Field


class CallTimeouts(BaseModel):
    """The three limits that bound one upstream tool call."""

    model_config = ConfigDict(frozen=True)

    call: float = Field(description="Seconds of silence from the upstream before the call is cut")
    reset_on_progress: bool = Field(
        description="Whether a progress notification restarts the silence window"
    )
    max_total: float = Field(
        description="Seconds after which the call is cut regardless of progress"
    )
