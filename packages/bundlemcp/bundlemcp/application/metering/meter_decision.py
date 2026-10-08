from pydantic import BaseModel, ConfigDict, Field


class MeterDecision(BaseModel):
    """The metering hook's verdict on whether a call may proceed."""

    model_config = ConfigDict(frozen=True)

    allowed: bool = Field(description="Whether the caller may make this tool call")
    reason: str | None = Field(
        default=None,
        description="Machine-readable denial code, e.g. 'insufficient_credits'",
    )
    user_message: str | None = Field(
        default=None,
        max_length=2000,
        description="Text for the person behind the client, e.g. 'Your credits are used up. "
        "Top up at https://example.com/account'. On a denial it is returned verbatim as the "
        "tool's error result, so the model relays it; ignored when the call is allowed",
    )
