"""Cross-replica signaling: routes messages to replica-pinned objects.

One pattern subscription on bmcp:signal:* per replica. Publishing is the ONLY
delivery path — the publisher's own subscription receives the message too, so
every signal is handled exactly once by whichever replica owns the target
(stream queue, call handle, or reply future). No local fast path = no
duplicate-delivery edge cases; the cost is one sub-millisecond Redis hop.
"""

from bundlemcp.gateway.signals.cancel_signal import CancelSignal
from bundlemcp.gateway.signals.deliver_signal import DeliverSignal
from bundlemcp.gateway.signals.reply_signal import ReplySignal
from bundlemcp.gateway.signals.resume_signal import ResumeSignal
from bundlemcp.gateway.signals.signal_bus import SIGNAL_PATTERN, SignalBus
from bundlemcp.gateway.signals.signal_envelope import SignalEnvelope
from bundlemcp.store.redis import SIGNAL_CHANNEL

__all__ = [
    "SIGNAL_CHANNEL",
    "SIGNAL_PATTERN",
    "CancelSignal",
    "DeliverSignal",
    "ReplySignal",
    "ResumeSignal",
    "SignalBus",
    "SignalEnvelope",
]
