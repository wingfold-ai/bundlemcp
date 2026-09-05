from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResumeInputs(BaseModel):
    """What a modern client's retry carries for the upstream in passthrough mode."""

    model_config = ConfigDict(frozen=True)

    responses: dict[str, Any] = Field(
        description="The client's inputResponses, keyed as the upstream's inputRequests were"
    )
    upstream_state: str | None = Field(
        description="The upstream's own requestState from its input_required result"
    )
