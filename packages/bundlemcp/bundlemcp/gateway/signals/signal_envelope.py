from pydantic import BaseModel, Field

from bundlemcp.gateway.signals.cancel_signal import CancelSignal
from bundlemcp.gateway.signals.deliver_signal import DeliverSignal
from bundlemcp.gateway.signals.reply_signal import ReplySignal


class SignalEnvelope(BaseModel):
    """What travels on the cross-replica signal channel."""

    signal: CancelSignal | DeliverSignal | ReplySignal = Field(
        discriminator="type",
        description="The signal to act on, selected by its type field",
    )
