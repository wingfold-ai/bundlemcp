import asyncio
from dataclasses import dataclass, field


@dataclass
class CallHandle:
    """An in-flight tools/call on this replica (the target for cancellation)."""

    session_id: str
    request_id: str
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    progress_queue: asyncio.Queue = field(default_factory=asyncio.Queue)  # PROT-1
