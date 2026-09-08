"""Domain errors raised by services; app.py maps them to HTTP responses."""

from bundlemcp.application.errors.authorization_redirect_error import AuthorizationRedirectError
from bundlemcp.application.errors.conflict_error import ConflictError
from bundlemcp.application.errors.invalid_input_error import InvalidInputError
from bundlemcp.application.errors.not_found_error import NotFoundError
from bundlemcp.application.errors.oauth_error import OAuthError
from bundlemcp.application.errors.precondition_error import PreconditionError
from bundlemcp.application.errors.service_error import ServiceError
from bundlemcp.application.errors.unavailable_error import UnavailableError

__all__ = [
    "AuthorizationRedirectError",
    "ConflictError",
    "InvalidInputError",
    "NotFoundError",
    "OAuthError",
    "PreconditionError",
    "ServiceError",
    "UnavailableError",
]
