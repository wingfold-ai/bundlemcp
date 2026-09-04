"""Server-to-client requests relayed back down to the MCP client.

Each request goes out on the client's GET stream and its reply is awaited on a
correlation future, so the replica holding the stream answers it wherever the
call is running.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from fastmcp.client.elicitation import ElicitResult
from mcp.types import CreateMessageResult, Root

from bundlemcp.gateway.signals import SignalBus
from bundlemcp.gateway.streams import StreamRegistry


class RelayRejected(Exception):
    """The client answered a relayed request with an error."""


def _as_function(method: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """A plain coroutine function over a bound method.

    The upstream client library recognises handlers with ``inspect.isfunction``,
    which a bound method fails, so each relay method is offered through a
    function that forwards to it.
    """

    async def handler(*args: Any, **kwargs: Any) -> Any:
        return await method(*args, **kwargs)

    return handler


class ClientRelay:
    """The client-side capabilities an upstream may call on during one tool call.

    Only the capabilities the client advertised at initialize are offered to
    the upstream client; the rest stay unset so the upstream sees them as
    unsupported rather than failing mid-call.
    """

    def __init__(
        self, registry: StreamRegistry, signals: SignalBus, session_id: str, wait_timeout: float
    ) -> None:
        self._registry = registry
        self._signals = signals
        self._session_id = session_id
        self._wait_timeout = wait_timeout

    def client_kwargs(self, capabilities: Mapping[str, Any]) -> dict[str, Any]:
        """The handler keyword arguments for the upstream client, gated by capability."""
        # PROT-5: capability intersection; PROT-4 names the `roots` kwarg; PROT-7 logging
        offered: dict[str, tuple[str, Callable[..., Any]]] = {
            "elicitation": ("elicitation_handler", self.elicit),
            "sampling": ("sampling_handler", self.sample),
            "roots": ("roots", self.roots),
            "logging": ("log_handler", self.log),
        }
        return {
            kwarg: _as_function(handler)
            for capability, (kwarg, handler) in offered.items()
            if capability in capabilities
        }

    async def _roundtrip(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        correlation_id = uuid.uuid4().hex
        future = self._registry.register_reply(correlation_id)
        request = {"jsonrpc": "2.0", "id": correlation_id, "method": method, "params": params}
        await self._signals.deliver(self._session_id, request)
        try:
            reply = await asyncio.wait_for(future, timeout=self._wait_timeout)
        finally:
            self._registry.unregister_reply(correlation_id)
        if "error" in reply:
            raise RelayRejected(reply["error"].get("message", "client rejected request"))
        return reply.get("result", {})

    @staticmethod
    def _dump(params: Any) -> dict[str, Any]:
        return params.model_dump(by_alias=True, mode="json", exclude_none=True)

    async def elicit(self, message: Any, response_type: Any, params: Any, context: Any) -> Any:
        result = await self._roundtrip("elicitation/create", self._dump(params))
        return ElicitResult(action=result.get("action", "decline"), content=result.get("content"))

    async def sample(self, messages: Any, params: Any, context: Any) -> Any:
        result = await self._roundtrip("sampling/createMessage", self._dump(params))
        return CreateMessageResult.model_validate(result)

    async def roots(self, context: Any) -> list[Root]:
        result = await self._roundtrip("roots/list", {})
        return [Root.model_validate(r) for r in result.get("roots", [])]

    async def log(self, message: Any) -> None:
        await self._signals.deliver(
            self._session_id,
            {"jsonrpc": "2.0", "method": "notifications/message", "params": self._dump(message)},
        )
