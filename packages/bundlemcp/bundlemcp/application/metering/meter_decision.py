from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from bundlemcp.application.metering.meter_context import SCRATCH_LIMIT_BYTES, scratch_size


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
    scratch: dict[str, Any] | None = Field(
        default=None,
        description="Data for this invocation's post_call, such as a reservation id; merged "
        f"into the context's scratch mapping. At most {SCRATCH_LIMIT_BYTES} bytes as JSON",
    )

    @field_validator("scratch")
    @classmethod
    def _bounded(cls, scratch: dict[str, Any] | None) -> dict[str, Any] | None:
        if scratch is not None and scratch_size(scratch) > SCRATCH_LIMIT_BYTES:
            raise ValueError(f"scratch exceeds {SCRATCH_LIMIT_BYTES} bytes as JSON")
        return scratch
