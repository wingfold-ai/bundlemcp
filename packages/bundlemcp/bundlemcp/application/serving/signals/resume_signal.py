from typing import Any, Literal

from pydantic import BaseModel, Field


class ResumeSignal(BaseModel):
    """An event of a call that a modern client's retry is waiting on elsewhere."""

    type: Literal["resume"] = Field(default="resume", description="Discriminator for the envelope")
    correlation_id: str = Field(description="The call whose retry should receive the event")
    phase: str = Field(
        description="'claimed' when the parked call took the retry's answers, 'event' for a "
        "notification, 'input_required' for another round, 'result' for the final message"
    )
    payload: dict[str, Any] = Field(description="The event, as the client should see it")
