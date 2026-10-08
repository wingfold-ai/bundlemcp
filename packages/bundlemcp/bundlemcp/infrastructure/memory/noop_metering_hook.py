from bundlemcp.application.metering.meter_context import MeterContext
from bundlemcp.application.metering.meter_decision import MeterDecision
from bundlemcp.application.metering.meter_outcome import MeterOutcome


class NoopMeteringHook:
    async def pre_call(self, ctx: MeterContext) -> MeterDecision:
        return MeterDecision(allowed=True)

    async def post_call(self, ctx: MeterContext, outcome: MeterOutcome, duration_ms: int) -> None:
        return None
