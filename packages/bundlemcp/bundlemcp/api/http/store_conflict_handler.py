"""The answer when a write lost a race with a concurrent write."""

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse

from bundlemcp.application.contracts.persistence.store_conflict import StoreConflict

log = structlog.get_logger(__name__)

CONFLICT_DETAIL = "the write collided with a concurrent change; read the resource again and retry"


async def store_conflict_handler(request: Request, exc: Exception) -> JSONResponse:
    """409 with a retryable message, rather than an unhandled 500 that drops the connection.

    An MCP endpoint answers with a JSON-RPC error; the management API and the
    OAuth routes with a problem body. The broken rule is logged, never a value.
    """
    if not isinstance(exc, StoreConflict):
        raise TypeError(f"store_conflict_handler handles StoreConflict, not {type(exc).__name__}")
    log.warning("store.conflict", path=request.url.path, constraint=str(exc))
    if request.url.path.endswith("/mcp"):
        return JSONResponse(
            status_code=409,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32000, "message": CONFLICT_DETAIL},
            },
        )
    return JSONResponse(status_code=409, content={"detail": CONFLICT_DETAIL})
