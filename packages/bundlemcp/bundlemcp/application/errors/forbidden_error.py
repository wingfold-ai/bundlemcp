from bundlemcp.application.errors.service_error import ServiceError


class ForbiddenError(ServiceError):
    """The caller is known but may not do this."""

    status = 403
