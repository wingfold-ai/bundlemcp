"""Redis-backed rate limiting (spec 16).

Fixed-window counter via atomic INCR + EXPIRE, bucketed by Redis server time
so all replicas share the window (RATE-2, ARC-9/ARC-15). Fails open on Redis
trouble unless the caller asks for fail-closed (RATE-6).
"""

from dataclasses import dataclass

import structlog
from redis.asyncio import Redis

from bundlemcp.gateway.metrics import (
    AUTH_FAILURE_LOCKOUTS,
    AUTH_FAILURES,
    RATE_LIMIT_FAIL_OPEN,
    Counters,
)

log = structlog.get_logger(__name__)

# key layout: bmcp:rate:{scope}:{bucket}
RATE_KEY = "bmcp:rate:{scope}:{bucket}"


@dataclass
class RateResult:
    allowed: bool
    retry_after: int = 0  # seconds until the window rolls over
    remaining: int = 0


class RateLimiter:
    def __init__(self, redis: Redis, counters: Counters | None = None) -> None:
        self._redis = redis
        self._counters = counters or Counters()

    async def _now(self) -> int:
        """Redis server time in whole seconds (RATE-7: shared clock)."""
        secs, _micros = await self._redis.time()
        return int(secs)

    async def check(
        self, scope: str, limit: int, window: int, *, fail_closed: bool = False
    ) -> RateResult:
        try:
            now = await self._now()
            bucket = now // window
            key = RATE_KEY.format(scope=scope, bucket=bucket)
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, window * 2)  # survive a full window
            if count <= limit:
                return RateResult(allowed=True, remaining=max(0, limit - count))
            return RateResult(allowed=False, retry_after=window - (now % window), remaining=0)
        except Exception:
            # RATE-6: availability over throttling — fail open (or closed on request), loudly.
            self._counters.inc(RATE_LIMIT_FAIL_OPEN)
            log.warning("ratelimit.redis_unavailable", scope=scope, fail_closed=fail_closed)
            if fail_closed:
                return RateResult(allowed=False, retry_after=window)
            return RateResult(allowed=True)


class AuthFailureLimiter:
    """RATE-5: gateway-wide credential-scan protection, keyed by client IP.

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

    async def record_failure(self, client_ip: str) -> RateResult:
        """Count one auth failure for this IP and report whether it is now locked out."""
        self._counters.inc(AUTH_FAILURES)
        result = await self._limiter.check(f"authfail:{client_ip}", self._limit, self._window)
        if not result.allowed:
            self._counters.inc(AUTH_FAILURE_LOCKOUTS)
        return result
