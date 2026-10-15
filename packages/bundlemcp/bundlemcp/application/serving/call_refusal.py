from pydantic import BaseModel, ConfigDict, Field


class CallRefusal(BaseModel):
    """A call stage's reason to end a call before the upstream is reached."""

    model_config = ConfigDict(frozen=True)

    reason: str = Field(description="Machine-readable code, e.g. 'insufficient_credits'")
    user_message: str | None = Field(
        default=None,
        description="Text for the person behind the client, answered verbatim as the tool's "
        "error result; None answers a JSON-RPC error carrying the reason",
    )
