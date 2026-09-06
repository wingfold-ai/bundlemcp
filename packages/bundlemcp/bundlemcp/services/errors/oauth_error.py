from bundlemcp.services.errors.service_error import ServiceError


class OAuthError(ServiceError):
    """A failure the OAuth protocol has a name for (RFC 6749 section 5.2)."""

    status = 400

    def __init__(self, error: str, description: str = "", *, status: int | None = None) -> None:
        # invalid_client is the one RFC 6749 error answered with 401
        self.error = error
        self.description = description
        if status is not None:
            self.status = status
        super().__init__(description or error)
