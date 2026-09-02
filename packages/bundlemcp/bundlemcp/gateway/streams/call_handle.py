import asyncio

from pydantic import BaseModel, ConfigDict, Field


class CallHandle(BaseModel):
    """An in-flight tools/call on this replica (the target for cancellation)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: str = Field(description="Session the call belongs to")
    request_id: str = Field(description="JSON-RPC id the client used, for matching cancellations")
    cancel_event: asyncio.Event = Field(
        default_factory=asyncio.Event,
        description="Set when a cancellation arrives for this call",
    )
    progress_queue: asyncio.Queue = Field(  # PROT-1
        default_factory=asyncio.Queue,
        description="Progress notifications from the upstream, drained by the SSE writer",
    )
