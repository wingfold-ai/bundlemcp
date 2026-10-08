"""The answer when the live-state store cannot be reached.

Sessions, rate-limit counters and login state live in Valkey. When it is down,
a request that needs it cannot be served, and it must not be answered as if
the session were gone: a 404 would make the client discard a session that
resumes once the store is back. The composition root registers this handler
for the store client's connection and timeout errors.
"""

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse

log = structlog.get_logger("bundlemcp.api.http.live_state_unavailable_handler")

# Seconds a client should wait before retrying; the store client has already
# retried the connection inside the request.
RETRY_AFTER_SECONDS = 1


async def live_state_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    """Answer 503 with ``Retry-After`` instead of an unhandled server error."""
    # SES-14: Redis down → 503 + Retry-After, never a false 404.
    log.warning("livestate.unavailable", path=request.url.path, error=type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={"detail": "live state store unavailable, retry shortly"},
        headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
    )
