"""Refusing a client that has failed authentication too often, in the protocol's own terms."""

from fastapi import Request, Response

from bundlemcp.api.http.auth_failure_guard import AuthFailureGuard
from bundlemcp.api.oauth.oauth_error_response import oauth_error_response
from bundlemcp.api.oauth.providers import AuthFailureGuardProvider
from bundlemcp.domain.oauth.oauth_error_code import OAuthErrorCode


class LockedOut(Exception):
    """The client's standing forbids answering; carries how long it must wait."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"locked out for {retry_after}s")


class AuthLockout:
    """Router-level dependency: a locked-out client is refused before any credential is read."""

    async def __call__(self, request: Request, guard: AuthFailureGuardProvider) -> None:
        # RATE-5: the check comes first, so a correct guess is refused too
        standing = await guard.locked_out(request)
        if not standing.allowed:
            raise LockedOut(standing.retry_after)


async def count_credential_failure(request: Request, guard: AuthFailureGuard) -> None:
    """Record one bad credential; the failure that exhausts the budget is answered as a lockout."""
    result = await guard.record(request)  # RATE-5
    if not result.allowed:
        raise LockedOut(result.retry_after)


async def locked_out_handler(request: Request, exc: LockedOut) -> Response:
    response = oauth_error_response(
        OAuthErrorCode.TOO_MANY_REQUESTS, "too many authentication failures", status=429
    )
    response.headers["Retry-After"] = str(exc.retry_after)
    return response
