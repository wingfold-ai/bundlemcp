"""The answer when the durable store cannot be reached."""

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse

from bundlemcp.application.contracts.persistence.store_unavailable import StoreUnavailable

log = structlog.get_logger(__name__)

# seconds a client should wait before retrying the request
RETRY_AFTER_SECONDS = 2


async def store_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    """503 with ``Retry-After``: a credential is never refused and nothing is half answered.

    An MCP endpoint answers with a JSON-RPC error; the management API and the
    OAuth routes with a problem body.
    """
    assert isinstance(exc, StoreUnavailable)
    log.warning("store.unavailable", path=request.url.path, error=str(exc))
    headers = {"Retry-After": str(RETRY_AFTER_SECONDS)}
    if request.url.path.endswith("/mcp"):
        return JSONResponse(
            status_code=503,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32000, "message": "the gateway's database is down; retry"},
            },
            headers=headers,
        )
    return JSONResponse(
        status_code=503,
        content={"detail": "the gateway's database is unavailable, retry shortly"},
        headers=headers,
    )
