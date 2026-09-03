from typing import Literal, Protocol, runtime_checkable

from bundlemcp.gateway.metering.meter_context import MeterContext
from bundlemcp.gateway.metering.meter_decision import MeterDecision

# Versioned and semver-relevant: consumers implement against this contract.
METERING_PROTOCOL_VERSION = 1


@runtime_checkable
class MeteringHook(Protocol):
    async def pre_call(self, ctx: MeterContext) -> MeterDecision: ...

    async def post_call(
        self, ctx: MeterContext, status: Literal["success", "error"], duration_ms: int
    ) -> None: ...
