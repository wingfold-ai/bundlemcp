from pydantic import BaseModel, Field


class RateResult(BaseModel):
    """Verdict for one rate-limit window check."""

    allowed: bool = Field(description="Whether this request may proceed")
    retry_after: int = Field(
        default=0, description="Seconds until the window rolls over and capacity returns"
    )
    remaining: int = Field(default=0, description="Requests still permitted in the current window")
