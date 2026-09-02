from pydantic import BaseModel, ConfigDict, Field


class MeterDecision(BaseModel):
    """The metering hook's verdict on whether a call may proceed."""

    model_config = ConfigDict(frozen=True)

    allowed: bool = Field(description="Whether the caller may make this tool call")
    reason: str | None = Field(
        default=None,
        description="Machine-readable denial code, e.g. 'insufficient_credits'",
    )
