from pydantic import BaseModel, Field

from bundlemcp.application.serving.signals.cancel_signal import CancelSignal
from bundlemcp.application.serving.signals.deliver_signal import DeliverSignal
from bundlemcp.application.serving.signals.reply_signal import ReplySignal
from bundlemcp.application.serving.signals.resume_signal import ResumeSignal


class SignalEnvelope(BaseModel):
    """What travels on the cross-replica signal channel."""

    signal: CancelSignal | DeliverSignal | ReplySignal | ResumeSignal = Field(
        discriminator="type",
        description="The signal to act on, selected by its type field",
    )
