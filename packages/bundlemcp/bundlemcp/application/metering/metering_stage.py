import structlog
from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.application.contracts.live_state.paused_invocations import PausedInvocations
from bundlemcp.application.metering.meter_context import SCRATCH_LIMIT_BYTES, scratch_size
from bundlemcp.application.metering.meter_outcome import MeterOutcome
from bundlemcp.application.metering.metering_hook import MeteringHook
from bundlemcp.application.metering.paused_invocation import PausedInvocation
from bundlemcp.application.serving.call_refusal import CallRefusal
from bundlemcp.application.serving.call_settlement import CallSettlement
from bundlemcp.application.serving.chain_call import ChainCall
from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.domain.bundles.presented_tool import PresentedTool

log = structlog.get_logger(__name__)

METERING_UNAVAILABLE = "metering_unavailable"


class MeteringStage(BaseModel):
    """Asks the metering hook once per invocation, and tells it once how the invocation ended.

    A later leg of an invocation that paused for client input claims the
    paused record instead of asking again. Whoever claims that record, a later
    leg, the leg that paused, or the expiry sweep, is the one that reports.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    hook: MeteringHook = Field(description="The deployment's metering hook")
    invocations: PausedInvocations = Field(description="Invocations waiting for client input")
    fail_open: bool = Field(
        description="Whether a call proceeds when the hook fails to answer its pre-call"
    )

    def present(self, tool: PresentedTool, curation: BundleTool | None) -> PresentedTool | None:
        return tool

    async def admit(self, call: ChainCall) -> CallRefusal | None:
        if call.resumed and await self._resume(call):
            return None
        try:
            decision = await self.hook.pre_call(call.context)
        except Exception:
            log.error("metering.pre_call_failed", exc_info=True)
            # the hook may have debited before it failed to answer, so a
            # post-call is owed whichever way the policy decides.
            call.metered = True
            # fail-open is the gateway's policy, not the hook's property.
            return None if self.fail_open else CallRefusal(reason=METERING_UNAVAILABLE)
        if not decision.allowed:
            return CallRefusal(
                reason=decision.reason or "denied", user_message=decision.user_message
            )
        call.metered = True
        scratch = call.context.scratch
        scratch.update(decision.scratch or {})
        if scratch_size(scratch) > SCRATCH_LIMIT_BYTES:
            log.error("metering.scratch_too_large", limit=SCRATCH_LIMIT_BYTES)
            scratch.clear()
        return None

    async def _resume(self, call: ChainCall) -> bool:
        """Continue a paused invocation from its record; False when there is none."""
        key = call.context.idempotency_key
        try:
            paused = await self.invocations.claim(key)
        except Exception:
            log.warning("metering.invocation_claim_failed", exc_info=True)
            paused = None
        if paused is None:
            # lost with a Valkey restart, or never written: asking again
            # risks a second charge under the same key, never a lost one.
            log.warning("metering.invocation_record_missing", idempotency_key=key)
            return False
        call.context = paused.context
        call.metered = True
        return True

    async def pause(self, call: ChainCall, until: float) -> None:
        if not call.metered:
            return
        try:
            await self.invocations.pause(PausedInvocation(context=call.context, expires_at=until))
        except Exception:
            log.warning("metering.invocation_pause_failed", exc_info=True)
            return
        call.paused = True

    async def settle(self, call: ChainCall, settlement: CallSettlement) -> None:
        if not call.metered or settlement.outcome is None:
            return
        key = call.context.idempotency_key
        if call.paused:
            try:
                claimed = await self.invocations.claim(key)
            except Exception:
                log.warning("metering.invocation_claim_failed", exc_info=True)
                claimed = None
            call.paused = False
            if claimed is None:
                # a later leg or the expiry sweep took the invocation over
                log.info("metering.invocation_settled_elsewhere", idempotency_key=key)
                call.metered = False
                return
        call.metered = False
        await self._report(call, settlement.outcome, settlement.duration_ms or 0)

    async def _report(self, call: ChainCall, outcome: MeterOutcome, duration_ms: int) -> None:
        try:
            await self.hook.post_call(call.context, outcome, duration_ms)
        except Exception:
            log.error("metering.post_call_failed", exc_info=True)
