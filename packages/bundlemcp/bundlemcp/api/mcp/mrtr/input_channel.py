from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class InputChannel(Protocol):
    """How an upstream's request for client input is answered for a modern-era client.

    The handshake era answers on the client's GET stream; the modern era either
    parks the call until the client retries with answers, or answers from the
    answers a retry already carries.
    """

    async def ask(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """The client's response to one request, as a JSON object."""
        ...
