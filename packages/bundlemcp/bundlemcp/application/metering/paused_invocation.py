from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.application.metering.meter_context import MeterContext


class PausedInvocation(BaseModel):
    """A metered tool call waiting for its client to answer a request for input.

    Its later legs continue from this record instead of asking the metering
    hook again; if none arrives before ``expires_at`` the invocation is closed
    with a post-call ``no_result``.
    """

    model_config = ConfigDict(frozen=True)

    context: MeterContext = Field(
        description="The context the invocation's pre_call ran with, scratch included"
    )
    expires_at: float = Field(
        description="Unix time the invocation's requestState expires; no later leg is accepted "
        "after it"
    )
