"""Per-replica registries for live streams and in-flight calls.

These hold the ONLY replica-pinned objects the architecture permits: open
HTTP streams and the asyncio primitives attached to them. Everything else
stays in Redis; cross-replica messages reach these objects via the SignalBus.
"""

from bundlemcp.gateway.streams.call_handle import CallHandle
from bundlemcp.gateway.streams.stream_key import StreamKey
from bundlemcp.gateway.streams.stream_registry import STREAM_CLOSING, StreamRegistry

__all__ = [
    "STREAM_CLOSING",
    "CallHandle",
    "StreamKey",
    "StreamRegistry",
]
