"""Where a modern-era call's events go: its own response stream, or, once parked, the bus."""

import asyncio
from typing import Any

from bundlemcp.application.contracts.live_state.signal_bus import SignalBus

Phase = str  # "event" | "claimed" | "input_required" | "result"


class CallEvents:
    """The sink for everything a call sends the client after the request was accepted.

    While the original response stream is open the events go straight to its
    queue. After the call has asked the client for input, the response that
    carried the ask is over, and every later event is published under the
    call's correlation id so that the replica serving the client's retry
    delivers it.
    """

    def __init__(self, correlation_id: str, local: asyncio.Queue, signals: SignalBus) -> None:
        self._correlation_id = correlation_id
        self._local = local
        self._signals = signals
        self._parked = False

    @property
    def correlation_id(self) -> str:
        return self._correlation_id

    @property
    def parked(self) -> bool:
        """Whether the call has asked the client for input and now outlives its response."""
        return self._parked

    async def emit(self, phase: Phase, payload: dict[str, Any]) -> None:
        if self._parked:
            await self._signals.resume(self._correlation_id, phase, payload)
            return
        await self._local.put((phase, payload))
        if phase == "input_required":
            self._parked = True
