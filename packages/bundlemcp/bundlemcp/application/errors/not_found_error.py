from bundlemcp.application.errors.service_error import ServiceError


class NotFoundError(ServiceError):
    """The referenced resource does not exist."""

    status = 404
