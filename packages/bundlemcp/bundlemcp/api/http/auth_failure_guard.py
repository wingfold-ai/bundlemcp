"""Counting failed authentications per client IP, for every edge that accepts credentials."""

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from bundlemcp.api.http.client_ip import client_ip
from bundlemcp.application.contracts.live_state.auth_failure_limiter import AuthFailureLimiter
from bundlemcp.application.contracts.live_state.rate_result import RateResult
from bundlemcp.application.settings.settings import Settings


class AuthFailureGuard:
    """Locks a client IP out after repeated bad credentials, however they were presented.

    An edge asks ``locked_out`` before it evaluates a credential, so a locked
    IP gets no answer at all — not even for a correct guess — and ``record``
    after a credential failed. Fails open when the live store is unreachable:
    availability beats lockout.
    """

    def __init__(self, limiter: AuthFailureLimiter, settings: Settings) -> None:
        self._limiter = limiter
        self._settings = settings

    async def locked_out(self, request: Request) -> RateResult:
        """The request's client standing before any credential is looked at."""
        # EP-20: the guard has to come first, or a locked-out scanner still
        # has every guess evaluated and a lucky one still answered.
        return await self._limiter.locked_out(client_ip(request, self._settings))

    async def record(self, request: Request) -> RateResult:
        """Count one failure for the request's client and report whether it is locked out."""
        return await self._limiter.record_failure(client_ip(request, self._settings))

    async def rejection_if_locked(self, request: Request) -> Response | None:
        """The MCP edge's pre-check: a 429 when the client is locked out, else None."""
        return self._render(await self.locked_out(request))

    async def note_failure(self, request: Request) -> Response | None:
        """The MCP edge's rendering: a 429 with Retry-After when locked out, else None."""
        return self._render(await self.record(request))

    @staticmethod
    def _render(result: RateResult) -> Response | None:
        if result.allowed:
            return None
        response = JSONResponse({"error": "too_many_auth_failures"}, status_code=429)
        response.headers["Retry-After"] = str(result.retry_after)
        return response
