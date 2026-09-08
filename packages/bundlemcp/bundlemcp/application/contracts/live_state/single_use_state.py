from typing import Protocol, runtime_checkable

from pydantic import BaseModel


@runtime_checkable
class SingleUseState[T: BaseModel](Protocol):
    """A typed record parked under an unguessable token, readable exactly once.

    Used wherever a flow leaves the gateway and comes back: the token travels
    in a redirect or a form and proves the return belongs to the departure.
    """

    async def put(self, value: T, *, token: str | None = None) -> str:
        """Store the record and return the token that retrieves it.

        A caller that already handed a token to a third party (an OAuth ``state``)
        passes it in; otherwise an unguessable one is generated.
        """
        ...

    async def take(self, token: str) -> T | None:
        """Retrieve and delete; None when unknown, expired, already taken or malformed."""
        ...
