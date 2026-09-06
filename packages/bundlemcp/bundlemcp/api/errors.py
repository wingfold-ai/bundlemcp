"""Domain errors to HTTP responses.

The service layer stays framework-free, so it raises `ServiceError` subclasses
rather than `HTTPException`. Each error class declares the status it maps to;
registered once on the app, this handler covers every route without a router
needing to catch anything.
"""

from fastapi import Request
from fastapi.responses import JSONResponse

from bundlemcp.services.errors import ServiceError


async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    """Render a domain error as FastAPI's own `{"detail": ...}` error shape."""
    return JSONResponse(status_code=exc.status, content={"detail": str(exc)})
