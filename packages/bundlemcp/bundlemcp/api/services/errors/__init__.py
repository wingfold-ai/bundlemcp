"""Domain errors raised by services; app.py maps them to HTTP responses."""

from bundlemcp.api.services.errors.conflict_error import ConflictError
from bundlemcp.api.services.errors.invalid_input_error import InvalidInputError
from bundlemcp.api.services.errors.not_found_error import NotFoundError
from bundlemcp.api.services.errors.precondition_error import PreconditionError
from bundlemcp.api.services.errors.service_error import ServiceError
from bundlemcp.api.services.errors.unavailable_error import UnavailableError

__all__ = [
    "ConflictError",
    "InvalidInputError",
    "NotFoundError",
    "PreconditionError",
    "ServiceError",
    "UnavailableError",
]
