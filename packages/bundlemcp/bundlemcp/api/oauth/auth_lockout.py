"""The router-level check that keeps a locked-out client off every authenticated route."""

from fastapi import Request

from bundlemcp.api.oauth.locked_out import LockedOut
from bundlemcp.api.oauth.providers import AuthFailureGuardProvider


class AuthLockout:
    """Router-level dependency: a locked-out client is refused before any credential is read."""

    async def __call__(self, request: Request, guard: AuthFailureGuardProvider) -> None:
        # RATE-5: the check comes first, so a correct guess is refused too
        standing = await guard.locked_out(request)
        if not standing.allowed:
            raise LockedOut(standing.retry_after)
