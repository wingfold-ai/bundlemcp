from bundlemcp.application.errors.service_error import ServiceError
from bundlemcp.domain.oauth.oauth_error_code import OAuthErrorCode

# RFC 6749 section 5.2: invalid_client is the one code answered with 401; the
# lockout is a 429 (RFC 6585); everything else the protocol names is a 400.
_STATUS_BY_CODE = {
    OAuthErrorCode.INVALID_CLIENT: 401,
    OAuthErrorCode.TOO_MANY_REQUESTS: 429,
}


class OAuthError(ServiceError):
    """A failure the OAuth protocol has a name for; the code decides the HTTP status."""

    def __init__(self, code: OAuthErrorCode, description: str = "") -> None:
        self.code = code
        self.description = description
        super().__init__(description or code.value)

    @property
    def status(self) -> int:  # type: ignore[override]
        return _STATUS_BY_CODE.get(self.code, 400)
