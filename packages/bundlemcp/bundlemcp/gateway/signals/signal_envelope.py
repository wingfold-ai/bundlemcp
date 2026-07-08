from pydantic import BaseModel, Field

from bundlemcp.gateway.signals.cancel_signal import CancelSignal
from bundlemcp.gateway.signals.deliver_signal import DeliverSignal
from bundlemcp.gateway.signals.reply_signal import ReplySignal


class SignalEnvelope(BaseModel):
    signal: CancelSignal | DeliverSignal | ReplySignal = Field(discriminator="type")
