from bundlemcp.services.errors.service_error import ServiceError


class NotFoundError(ServiceError):
    """The referenced resource does not exist (HTTP 404)."""
