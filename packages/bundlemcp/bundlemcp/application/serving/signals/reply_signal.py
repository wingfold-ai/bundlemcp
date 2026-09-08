from typing import Any, Literal

from pydantic import BaseModel, Field


class ReplySignal(BaseModel):
    """Route a client's reply back to the replica awaiting it."""

    type: Literal["reply"] = Field(default="reply", description="Discriminator for the envelope")
    correlation_id: str = Field(description="Id of the server-to-client request being answered")
    payload: dict[str, Any] = Field(description="The client's JSON-RPC response")
