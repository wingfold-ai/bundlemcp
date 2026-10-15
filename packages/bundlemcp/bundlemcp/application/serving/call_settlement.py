from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.application.metering.meter_outcome import MeterOutcome
from bundlemcp.domain.audit.audit_status import AuditStatus


class CallSettlement(BaseModel):
    """How one leg of a tool call ended, as every call stage is told."""

    model_config = ConfigDict(frozen=True)

    status: AuditStatus = Field(description="The leg's audit status")
    outcome: MeterOutcome | None = Field(
        description="How the invocation ended, for metering; None when the leg ended waiting "
        "for client input and the invocation continues on a later leg"
    )
    duration_ms: int | None = Field(
        default=None, ge=0, description="Milliseconds the leg took; None when it never ran"
    )
    denied_reason: str | None = Field(
        default=None, description="Why a stage refused the call, when one did"
    )
    error_message: str | None = Field(default=None, description="Why the call failed, when it did")

    @classmethod
    def refused(cls, reason: str) -> "CallSettlement":
        """A call a stage refused before the upstream was reached."""
        return cls(status=AuditStatus.DENIED, outcome=MeterOutcome.NO_RESULT, denied_reason=reason)

    @classmethod
    def failed(cls, error_message: str) -> "CallSettlement":
        """A call the gateway could not make, before the upstream was reached."""
        return cls(
            status=AuditStatus.ERROR, outcome=MeterOutcome.NO_RESULT, error_message=error_message
        )
