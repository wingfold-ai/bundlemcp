from bundlemcp.services.errors.service_error import ServiceError


class ConflictError(ServiceError):
    """The operation conflicts with current state."""

    status = 409
