"""How the edge frames a JSON-RPC message as a server-sent event."""

import json
from typing import Any

SSE_HEADERS = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
KEEPALIVE_SECONDS = 15
SSE_KEEPALIVE = ": keepalive\n\n"


def sse_data(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"
