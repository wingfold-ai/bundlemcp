from bundlemcp.services.errors.service_error import ServiceError


class UnavailableError(ServiceError):
    """A required collaborator is not available right now (HTTP 503)."""
