from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class ResourceSubscription(BaseModel):
    """One stream's subscription to updates of one member resource."""

    model_config = ConfigDict(frozen=True)

    server_name: str = Field(description="The member server that owns the resource")
    uri: str = Field(description="The resource's URI as the member names it")


@runtime_checkable
class ResourceSubscriptions(Protocol):
    """Which client streams want updates of which member resources, shared by every replica.

    A stream is a handshake client's session or a modern client's listen
    stream, addressed by the id its notifications are delivered to.
    """

    async def subscribe(self, stream_id: str, subscription: ResourceSubscription) -> None: ...

    async def unsubscribe(self, stream_id: str, subscription: ResourceSubscription) -> None: ...

    async def streams(self, subscription: ResourceSubscription) -> list[str]:
        """The streams subscribed to one resource."""
        ...

    async def of_stream(self, stream_id: str) -> list[ResourceSubscription]:
        """What one stream is subscribed to."""
        ...

    async def drop_stream(self, stream_id: str) -> list[ResourceSubscription]:
        """Forget every subscription of a stream that closed, returning what it held."""
        ...
