"""What a tools/call carries once its chain has admitted it."""

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.application.serving.call_handle import CallHandle
from bundlemcp.domain.config.call_timeouts import CallTimeouts


class AdmittedCall(BaseModel):
    """The facts every step after admission needs, settled once before the upstream is driven.

    Built only after the headers resolved and every call stage admitted the
    call, so a step that takes one cannot run on a call that was refused.
    """

    model_config = ConfigDict(frozen=True)

    forwarded: dict[str, str] = Field(
        description="The caller's headers this member is configured to receive"
    )
    credentials: dict[str, str] = Field(
        description="The gateway's credential headers for the member, such as its upstream "
        "OAuth bearer; they win over a forwarded header of the same name"
    )
    timeouts: CallTimeouts = Field(description="The time budgets the upstream call runs under")
    handle: CallHandle | None = Field(
        description="Where a cancellation of this call arrives; None when the request has no "
        "id, so nothing can cancel the call"
    )
