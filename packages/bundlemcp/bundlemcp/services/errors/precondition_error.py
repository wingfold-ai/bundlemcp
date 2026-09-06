from bundlemcp.services.errors.service_error import ServiceError


class PreconditionError(ServiceError):
    """A deployment/config precondition is not met."""

    status = 400
