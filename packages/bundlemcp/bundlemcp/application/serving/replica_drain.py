"""Shutting one replica down within a known bound."""

import asyncio
from collections.abc import Awaitable, Callable

import structlog

from bundlemcp.application.contracts.live_state.stream_registry import StreamRegistry

log = structlog.get_logger(__name__)

# calls are cancelled this long before the drain window closes, so each can still answer
CANCEL_MARGIN_SECONDS = 1.0


class ReplicaDrain:
    """What happens on this replica between the stop signal and the exit.

    ``begin`` marks the replica as draining, which readiness and the MCP edge
    read to report not ready and refuse new requests; it ends every
    notification stream the replica holds; and it schedules the cancellation
    of every call still running shortly before the drain window ends, so each
    answers its client with an error and tells metering it was cancelled
    instead of being cut off by the server's own deadline.
    """

    def __init__(
        self,
        registry: StreamRegistry,
        drain_seconds: float,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._registry = registry
        self._drain_seconds = drain_seconds
        self._sleep = sleep
        self._draining = False
        self._deadline: asyncio.Task[None] | None = None

    @property
    def draining(self) -> bool:
        return self._draining

    def begin(self) -> None:
        """Start draining; calling it again changes nothing."""
        if self._draining:
            return
        self._draining = True
        log.info("replica.draining", drain_seconds=self._drain_seconds)
        self._registry.close_streams()
        self._deadline = asyncio.create_task(self._cancel_at_deadline(), name="drain_deadline")

    async def _cancel_at_deadline(self) -> None:
        await self._sleep(max(0.0, self._drain_seconds - CANCEL_MARGIN_SECONDS))
        cancelled = self._registry.cancel_calls()
        if cancelled:
            log.warning("replica.calls_cancelled_at_drain_deadline", calls=cancelled)

    def stop(self) -> None:
        """Forget the deadline once the replica has drained."""
        if self._deadline is not None:
            self._deadline.cancel()
            self._deadline = None
