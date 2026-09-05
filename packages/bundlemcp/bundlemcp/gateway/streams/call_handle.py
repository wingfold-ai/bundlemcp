import asyncio

from pydantic import BaseModel, ConfigDict, Field


class CallHandle(BaseModel):
    """An in-flight tools/call on this replica (the target for cancellation)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    routing_key: str = Field(
        description="Session id or per-request id the call is addressed by from other replicas"
    )
    request_id: str = Field(description="JSON-RPC id the client used, for matching cancellations")
    cancel_event: asyncio.Event = Field(
        default_factory=asyncio.Event,
        description="Set when a cancellation arrives for this call",
    )
