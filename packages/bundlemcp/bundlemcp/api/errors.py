"""Domain errors to HTTP responses.

The service layer stays framework-free, so it raises `ServiceError` subclasses
rather than `HTTPException`. This module is where those errors acquire a status
code — registered once on the app, it covers every route without a router
needing to catch anything.
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse

from bundlemcp.services.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PreconditionError,
    ServiceError,
    UnavailableError,
)

STATUS_BY_ERROR: dict[type[ServiceError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    InvalidInputError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    PreconditionError: status.HTTP_400_BAD_REQUEST,
    UnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
}


async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    """Render a domain error as FastAPI's own `{"detail": ...}` error shape."""
    code = STATUS_BY_ERROR.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
    return JSONResponse(status_code=code, content={"detail": str(exc)})
