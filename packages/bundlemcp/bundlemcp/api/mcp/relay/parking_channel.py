"""Park the upstream call until the modern client retries with its answers (PROT-18)."""

import asyncio
from collections.abc import Callable
from typing import Any

from bundlemcp.api.mcp.relay.call_events import CallEvents
from bundlemcp.api.mcp.relay.input_required_result import input_required_result
from bundlemcp.api.mcp.relay.relay_rejected import RelayRejected
from bundlemcp.application.contracts.live_state.stream_registry import StreamRegistry

Shaper = Callable[[dict[str, Any]], dict[str, Any]]


class ParkingChannel:
    """One upstream request at a time becomes an input_required round for the client."""

    def __init__(
        self,
        registry: StreamRegistry,
        events: CallEvents,
        seal_state: Callable[[], str],
        shape: Shaper,
        wait_timeout: float,
    ) -> None:
        self._registry = registry
        self._events = events
        self._seal_state = seal_state
        self._shape = shape
        self._wait_timeout = wait_timeout
        self._round = 0

    async def ask(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._round += 1
        key = f"input-{self._round}"
        future = self._registry.register_reply(self._events.correlation_id)
        asked = input_required_result(
            {key: {"method": method, "params": params}}, self._seal_state()
        )
        await self._events.emit("input_required", {"result": self._shape(asked)})
        try:
            # PROT-6: the client's retry must arrive within the call's own budget.
            reply = await asyncio.wait_for(future, timeout=self._wait_timeout)
        finally:
            self._registry.unregister_reply(self._events.correlation_id)
        # The retry is being served somewhere; from here on events go to it.
        await self._events.emit("claimed", {})
        responses = reply.get("result") or {}
        answer = responses.get(key)
        if answer is None and len(responses) == 1:
            answer = next(iter(responses.values()))
        if not isinstance(answer, dict):
            raise RelayRejected("the client's retry carried no answer for this request")
        return answer
