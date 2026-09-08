from bundlemcp.application.metering.meter_context import MeterContext
from bundlemcp.application.metering.meter_decision import MeterDecision


class NoopMeteringHook:
    async def pre_call(self, ctx: MeterContext) -> MeterDecision:
        return MeterDecision(allowed=True)

    async def post_call(self, ctx, status, duration_ms) -> None:
        return None
