"""Refusing a client that has failed authentication too often, in the protocol's own terms."""

from fastapi import Request, Response

from bundlemcp.api.oauth.oauth_error_response import oauth_error_response
from bundlemcp.domain.oauth.oauth_error_code import OAuthErrorCode


class LockedOut(Exception):
    """The client's standing forbids answering; carries how long it must wait."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"locked out for {retry_after}s")


async def locked_out_handler(request: Request, exc: LockedOut) -> Response:
    """Answer a lockout as an OAuth error with the wait the client must observe."""
    response = oauth_error_response(
        OAuthErrorCode.TOO_MANY_REQUESTS, "too many authentication failures", status=429
    )
    response.headers["Retry-After"] = str(exc.retry_after)
    return response
