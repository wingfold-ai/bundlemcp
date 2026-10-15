from pydantic import BaseModel, Field

from bundlemcp.application.metering.meter_context import MeterContext
from bundlemcp.domain.audit.audit_context import AuditContext


class ChainCall(BaseModel):
    """One leg of a tool call as the chain's call stages see it.

    The stages record on it what they did, so a later method of the chain (and
    a later stage) knows: whether metering owes this invocation a post-call,
    and whether this leg left a paused-invocation record behind.
    """

    context: MeterContext = Field(description="The full context every call stage receives")
    audit: AuditContext = Field(description="What this leg's audit record says about the call")
    resumed: bool = Field(
        default=False,
        description="A later leg of an invocation that paused for client input; its first leg "
        "already ran pre_call",
    )
    metered: bool = Field(
        default=False,
        description="pre_call allowed this invocation, or failed to answer, so exactly one "
        "post_call is owed",
    )
    paused: bool = Field(
        default=False,
        description="This leg stored a paused-invocation record, which a later leg or the "
        "sweeper may have claimed since",
    )
