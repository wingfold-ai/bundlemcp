import structlog
from redis.asyncio import Redis

from bundlemcp.gateway.metrics import (
    RATE_LIMIT_FAIL_OPEN,
    Counters,
)
from bundlemcp.gateway.ratelimit.rate_result import RateResult

log = structlog.get_logger("bundlemcp.gateway.ratelimit")

RATE_KEY = "bmcp:rate:{scope}:{bucket}"


class RateLimiter:
    def __init__(self, redis: Redis, counters: Counters | None = None) -> None:
        self._redis = redis
        self._counters = counters or Counters()

    async def _now(self) -> int:
        """Redis server time in whole seconds — the clock shared by all replicas."""
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
