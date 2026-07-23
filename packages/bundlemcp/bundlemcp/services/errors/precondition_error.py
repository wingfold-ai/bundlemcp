from bundlemcp.services.errors.service_error import ServiceError


class PreconditionError(ServiceError):
    """A deployment/config precondition is not met (HTTP 400)."""
