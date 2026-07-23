"""Domain errors raised by services; app.py maps them to HTTP responses."""

from bundlemcp.services.errors.conflict_error import ConflictError
from bundlemcp.services.errors.invalid_input_error import InvalidInputError
from bundlemcp.services.errors.not_found_error import NotFoundError
from bundlemcp.services.errors.precondition_error import PreconditionError
from bundlemcp.services.errors.service_error import ServiceError
from bundlemcp.services.errors.unavailable_error import UnavailableError

__all__ = [
    "ConflictError",
    "InvalidInputError",
    "NotFoundError",
    "PreconditionError",
    "ServiceError",
    "UnavailableError",
]
