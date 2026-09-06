from bundlemcp.services.errors.service_error import ServiceError


class AuthorizationRedirectError(ServiceError):
    """An authorization request the client must learn about at its redirect URI.

    Raised only once the client and its redirect URI are known to be genuine, so
    the error can be delivered there instead of shown on the gateway.
    """

    def __init__(
        self,
        redirect_uri: str,
        state: str | None,
        error: str,
        description: str = "",
        *,
        issuer: str | None = None,
    ) -> None:
        # issuer is carried as `iss` on the redirect (RFC 9207) when known
        self.redirect_uri = redirect_uri
        self.state = state
        self.error = error
        self.description = description
        self.issuer = issuer
        super().__init__(description or error)
