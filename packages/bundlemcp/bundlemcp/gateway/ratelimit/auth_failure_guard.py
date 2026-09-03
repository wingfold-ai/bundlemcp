"""Counting failed authentications per client IP, for every edge that accepts credentials."""

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from bundlemcp.gateway.proxy import client_ip
from bundlemcp.gateway.ratelimit.auth_failure_limiter import AuthFailureLimiter
from bundlemcp.gateway.ratelimit.rate_result import RateResult
from bundlemcp.settings import Settings


class AuthFailureGuard:
    """Locks a client IP out after repeated bad credentials, however they were presented.

    Fails open when the live store is unreachable: availability beats lockout.
    """

    def __init__(self, limiter: AuthFailureLimiter, settings: Settings) -> None:
        self._limiter = limiter
        self._settings = settings

    async def record(self, request: Request) -> RateResult:
        """Count one failure for the request's client and report whether it is locked out."""
        # RATE-5
        return await self._limiter.record_failure(client_ip(request, self._settings))

    async def note_failure(self, request: Request) -> Response | None:
        """The MCP edge's rendering: a 429 with Retry-After when locked out, else None."""
        result = await self.record(request)
        if result.allowed:
            return None
        response = JSONResponse({"error": "too_many_auth_failures"}, status_code=429)
        response.headers["Retry-After"] = str(result.retry_after)
        return response
