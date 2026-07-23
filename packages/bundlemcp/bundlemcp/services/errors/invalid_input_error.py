from bundlemcp.services.errors.service_error import ServiceError


class InvalidInputError(ServiceError):
    """Input violates a domain rule (HTTP 422)."""
