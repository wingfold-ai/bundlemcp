from typing import Literal, Protocol

from bundlemcp.gateway.metering.meter_context import MeterContext
from bundlemcp.gateway.metering.meter_decision import MeterDecision


class MeteringHook(Protocol):
    async def pre_call(self, ctx: MeterContext) -> MeterDecision: ...

    async def post_call(
        self, ctx: MeterContext, status: Literal["success", "error"], duration_ms: int
    ) -> None: ...
