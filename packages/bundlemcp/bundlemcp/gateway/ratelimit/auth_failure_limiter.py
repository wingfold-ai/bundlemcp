from redis.asyncio import Redis

from bundlemcp.gateway.metrics import (
    AUTH_FAILURE_LOCKOUTS,
    AUTH_FAILURES,
    Counters,
)
from bundlemcp.gateway.ratelimit.rate_limiter import RateLimiter
from bundlemcp.gateway.ratelimit.rate_result import RateResult


class AuthFailureLimiter:
    """Gateway-wide credential-scan protection, keyed by client IP.

    Each authentication failure increments a per-IP fixed-window counter; once
    the configured threshold is exceeded the IP is locked out until the window
    rolls over. Always fails open on Redis trouble — availability beats lockout,
    with the same alarm metric the underlying limiter raises.
    """

    def __init__(
        self, redis: Redis, *, limit: int, window: int, counters: Counters | None = None
    ) -> None:
        self._counters = counters or Counters()
        self._limiter = RateLimiter(redis, self._counters)
        self._limit = limit
        self._window = window

    async def locked_out(self, client_ip: str) -> RateResult:
        """Whether this IP has already exhausted its budget, without counting anything."""
        return await self._limiter.peek(f"authfail:{client_ip}", self._limit, self._window)

    async def record_failure(self, client_ip: str) -> RateResult:
        """Count one auth failure for this IP and report whether it is now locked out."""
        self._counters.inc(AUTH_FAILURES)
        result = await self._limiter.check(f"authfail:{client_ip}", self._limit, self._window)
        if not result.allowed:
            self._counters.inc(AUTH_FAILURE_LOCKOUTS)
        return result
