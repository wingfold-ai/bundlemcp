"""An upstream's requests for client input, and its log messages, carried back to the client.

For a handshake-era client each request goes out on its GET stream and the
reply is awaited on a correlation future, so the replica holding the stream
answers it wherever the call is running. Log messages go the same way, or into
the call's own response stream when the caller supplies a sink for them.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from fastmcp.client.elicitation import ElicitResult
from mcp.types import CreateMessageResult, Root

from bundlemcp.api.mcp.protocol.log_levels import at_least
from bundlemcp.api.mcp.relay.input_channel import InputChannel
from bundlemcp.api.mcp.relay.relay_rejected import RelayRejected
from bundlemcp.application.contracts.live_state.signal_bus import SignalBus
from bundlemcp.application.contracts.live_state.stream_registry import StreamRegistry

NotificationSink = Callable[[dict[str, Any]], Awaitable[None]]


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
    """The client-side capabilities an upstream may call on during one call.

    Only the capabilities the client advertised are offered to the upstream
    client; the rest stay unset so the upstream sees them as unsupported rather
    than failing mid-call. Log messages are offered when the client asked for a
    level, and only those at or above it are relayed.
    """

    def __init__(
        self,
        registry: StreamRegistry,
        signals: SignalBus,
        routing_key: str,
        wait_timeout: float,
        *,
        log_level: str | None,
        on_notification: NotificationSink | None,
        channel: InputChannel | None,
    ) -> None:
        # on_notification is None when log messages belong on the client's own
        # notification stream (handshake era) rather than the call's response;
        # channel is None in the handshake era, where requests go out on that
        # stream, and set for a modern client (PROT-18)
        self._registry = registry
        self._signals = signals
        self._routing_key = routing_key
        self._wait_timeout = wait_timeout
        self._log_level = log_level
        self._on_notification = on_notification
        self._channel = channel

    def client_kwargs(self, capabilities: Mapping[str, Any]) -> dict[str, Any]:
        """The handler keyword arguments for the upstream client, gated by capability."""
        # PROT-5: capability intersection; PROT-4 names the `roots` kwarg
        offered: dict[str, tuple[str, Callable[..., Any]]] = {
            "elicitation": ("elicitation_handler", self.elicit),
            "sampling": ("sampling_handler", self.sample),
            "roots": ("roots", self.roots),
        }
        kwargs = {
            kwarg: _as_function(handler)
            for capability, (kwarg, handler) in offered.items()
            if capability in capabilities
        }
        if self._log_level is not None:  # PROT-7 / PROT-20
            kwargs["log_handler"] = _as_function(self.log)
        return kwargs

    async def _roundtrip(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._channel is not None:
            return await self._channel.ask(method, params)
        correlation_id = uuid.uuid4().hex
        future = self._registry.register_reply(correlation_id)
        request = {"jsonrpc": "2.0", "id": correlation_id, "method": method, "params": params}
        await self._signals.deliver(self._routing_key, request)
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
        if self._log_level is not None and not at_least(str(message.level), self._log_level):
            return
        payload = {
            "jsonrpc": "2.0",
            "method": "notifications/message",
            "params": self._dump(message),
        }
        if self._on_notification is not None:
            await self._on_notification(payload)
        else:
            await self._signals.deliver(self._routing_key, payload)
