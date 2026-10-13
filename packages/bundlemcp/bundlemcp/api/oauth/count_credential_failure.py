"""Recording one failed credential against the presenter's budget."""

from fastapi import Request

from bundlemcp.api.http.auth_failure_guard import AuthFailureGuard
from bundlemcp.api.oauth.locked_out import LockedOut


async def count_credential_failure(request: Request, guard: AuthFailureGuard) -> None:
    """Record one bad credential; the failure that exhausts the budget is answered as a lockout."""
    result = await guard.record(request)
    if not result.allowed:
        raise LockedOut(result.retry_after)
