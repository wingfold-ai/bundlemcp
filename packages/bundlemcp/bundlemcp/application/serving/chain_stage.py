from typing import Protocol, runtime_checkable

from bundlemcp.application.serving.call_refusal import CallRefusal
from bundlemcp.application.serving.call_settlement import CallSettlement
from bundlemcp.application.serving.chain_call import ChainCall
from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.domain.bundles.presented_tool import PresentedTool


@runtime_checkable
class ChainStage(Protocol):
    """One stage of the chain every listed and every called tool passes.

    A stage that only shapes tools returns the tool from ``present`` and does
    nothing in the other methods; a stage that only acts on calls returns the
    tool from ``present`` unchanged.
    """

    def present(self, tool: PresentedTool, curation: BundleTool | None) -> PresentedTool | None:
        """The tool as this stage shows it, or None to drop it from list and call alike."""
        ...

    async def admit(self, call: ChainCall) -> CallRefusal | None:
        """Before the upstream is reached: a refusal ends the call."""
        ...

    async def pause(self, call: ChainCall, until: float) -> None:
        """The leg waits for client input; the invocation may continue until Unix time ``until``."""
        ...

    async def settle(self, call: ChainCall, settlement: CallSettlement) -> None:
        """The leg ended; every stage hears it, including after a refusal."""
        ...
