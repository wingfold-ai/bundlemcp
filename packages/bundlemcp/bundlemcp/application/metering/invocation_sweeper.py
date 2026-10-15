"""Closing invocations whose client never came back with the input they were asked for."""

import structlog

from bundlemcp.application.contracts.live_state.paused_invocations import PausedInvocations
from bundlemcp.application.metering.meter_outcome import MeterOutcome
from bundlemcp.application.metering.metering_hook import MeteringHook
from bundlemcp.domain.shared.clock import Clock

log = structlog.get_logger(__name__)

BATCH_SIZE = 100


class InvocationSweeper:
    """Tells the metering hook ``no_result`` for every paused invocation past its expiry.

    Each record is claimed before it is reported, so an invocation a late
    leg claimed meanwhile is reported by that leg instead, never twice.
    """

    def __init__(self, invocations: PausedInvocations, hook: MeteringHook, clock: Clock) -> None:
        self._invocations = invocations
        self._hook = hook
        self._clock = clock

    async def sweep(self) -> int:
        """Close every overdue invocation; returns how many this sweep closed."""
        closed = 0
        while True:
            keys = await self._invocations.expired(self._clock.now().timestamp(), BATCH_SIZE)
            for key in keys:
                paused = await self._invocations.claim(key)
                if paused is None:
                    continue
                try:
                    await self._hook.post_call(paused.context, MeterOutcome.NO_RESULT, 0)
                except Exception:
                    log.error("metering.post_call_failed", exc_info=True)
                closed += 1
            if len(keys) < BATCH_SIZE:
                return closed
