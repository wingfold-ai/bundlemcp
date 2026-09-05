from typing import Any, Literal

from pydantic import BaseModel, Field


class DeliverSignal(BaseModel):
    """Push a message into a stream held open on another replica."""

    type: Literal["deliver"] = Field(
        default="deliver", description="Discriminator for the envelope"
    )
    stream_id: str = Field(description="Stream that should receive the message")
    payload: dict[str, Any] = Field(description="JSON-RPC message to write to that stream")
