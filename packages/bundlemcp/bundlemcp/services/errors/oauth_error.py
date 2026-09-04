from bundlemcp.services.errors.service_error import ServiceError


class OAuthError(ServiceError):
    """A failure the OAuth protocol has a name for (RFC 6749 section 5.2)."""

    def __init__(self, error: str, description: str = "", *, status: int = 400) -> None:
        self.error = error
        self.description = description
        self.status = status
        super().__init__(description or error)
