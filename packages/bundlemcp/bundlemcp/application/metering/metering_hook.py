from typing import Protocol, runtime_checkable

from bundlemcp.application.metering.meter_context import MeterContext
from bundlemcp.application.metering.meter_decision import MeterDecision
from bundlemcp.application.metering.meter_outcome import MeterOutcome

# Versioned and semver-relevant: consumers implement against this contract.
# 2: post_call reports a MeterOutcome instead of success/error.
METERING_PROTOCOL_VERSION = 2


@runtime_checkable
class MeteringHook(Protocol):
    async def pre_call(self, ctx: MeterContext) -> MeterDecision: ...

    async def post_call(
        self, ctx: MeterContext, outcome: MeterOutcome, duration_ms: int
    ) -> None: ...
