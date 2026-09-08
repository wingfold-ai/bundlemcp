from typing import Literal

from pydantic import BaseModel, Field


class CancelSignal(BaseModel):
    """Cancel an in-flight call on whichever replica is holding it."""

    type: Literal["cancel"] = Field(default="cancel", description="Discriminator for the envelope")
    routing_key: str = Field(description="Session whose call should be cancelled")
    request_id: str = Field(description="JSON-RPC id of the call to cancel")
