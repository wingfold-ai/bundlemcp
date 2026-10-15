from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.application.contracts.persistence.audit_sink import AuditSink
from bundlemcp.application.serving.call_refusal import CallRefusal
from bundlemcp.application.serving.call_settlement import CallSettlement
from bundlemcp.application.serving.chain_call import ChainCall
from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.domain.bundles.presented_tool import PresentedTool


class AuditStage(BaseModel):
    """The last stage: one audit record per leg, refusals included."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    sink: AuditSink = Field(description="Where the records go")

    def present(self, tool: PresentedTool, curation: BundleTool | None) -> PresentedTool | None:
        return tool

    async def admit(self, call: ChainCall) -> CallRefusal | None:
        return None

    async def pause(self, call: ChainCall, until: float) -> None:
        return None

    async def settle(self, call: ChainCall, settlement: CallSettlement) -> None:
        self.sink.record(
            call.audit.record(
                settlement.status,
                denied_reason=settlement.denied_reason,
                error_message=settlement.error_message,
                duration_ms=settlement.duration_ms,
            )
        )
