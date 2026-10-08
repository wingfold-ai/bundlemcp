"""The bodies the gateway POSTs to a billing service that meters over HTTP."""

from typing import Literal

from pydantic import BaseModel, Field

from bundlemcp.application.metering.meter_context import MeterContext
from bundlemcp.application.metering.meter_outcome import MeterOutcome
from bundlemcp.application.metering.metering_hook import METERING_PROTOCOL_VERSION


class PreCallEvent(BaseModel):
    """Asks whether a tool call may proceed; the answer is a MeterDecision."""

    protocol_version: int = Field(
        default=METERING_PROTOCOL_VERSION,
        description="Version of the metering contract this body follows",
    )
    event: Literal["pre_call"] = Field(
        default="pre_call", description="Which of the two metering events this is"
    )
    context: MeterContext = Field(description="The caller and the tool call being metered")


class PostCallEvent(BaseModel):
    """Reports how a tool call that was metered ended; any 2xx acknowledges it."""

    protocol_version: int = Field(
        default=METERING_PROTOCOL_VERSION,
        description="Version of the metering contract this body follows",
    )
    event: Literal["post_call"] = Field(
        default="post_call", description="Which of the two metering events this is"
    )
    context: MeterContext = Field(
        description="The same context the pre-call carried, idempotency key included"
    )
    outcome: MeterOutcome = Field(description="How the call ended")
    duration_ms: int = Field(
        ge=0, description="Milliseconds the upstream call took; 0 when it never ran"
    )
