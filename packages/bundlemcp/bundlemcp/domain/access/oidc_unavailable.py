from bundlemcp.domain.access.oidc_error import OidcError


class OidcUnavailable(OidcError):
    """The identity provider cannot be used yet; a login may be retried after ``retry_after``."""

    def __init__(self, message: str, *, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = retry_after
