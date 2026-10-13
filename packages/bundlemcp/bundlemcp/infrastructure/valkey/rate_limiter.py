import structlog
from redis.asyncio import Redis

from bundlemcp.application.contracts.live_state.counters import RATE_LIMIT_FAIL_OPEN, Counters
from bundlemcp.application.contracts.live_state.rate_result import RateResult
from bundlemcp.infrastructure.inprocess.counters import InProcessCounters

log = structlog.get_logger("bundlemcp.infrastructure.valkey.rate_limiter")

RATE_KEY = "bmcp:rate:{scope}:{bucket}"


class ValkeyRateLimiter:
    def __init__(self, redis: Redis, counters: Counters | None = None) -> None:
        self._redis = redis
        self._counters = counters or InProcessCounters()

    async def _now(self) -> int:
        """Redis server time in whole seconds — the clock shared by all replicas."""
        secs, _micros = await self._redis.time()
        return int(secs)

    async def check(
        self, scope: str, limit: int, window: int, *, fail_closed: bool = False
    ) -> RateResult:
        """Count one event in the scope's current window and report whether it fit."""
        try:
            now = await self._now()
            key = RATE_KEY.format(scope=scope, bucket=now // window)
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, window * 2)  # survive a full window
            return self._result(count, limit, window, now)
        except Exception:
            return self._fail(scope, window, fail_closed)

    async def peek(
        self, scope: str, limit: int, window: int, *, fail_closed: bool = False
    ) -> RateResult:
        """Report the scope's standing in the current window without counting anything."""
        try:
            now = await self._now()
            raw = await self._redis.get(RATE_KEY.format(scope=scope, bucket=now // window))
            return self._result(int(raw or 0), limit, window, now)
        except Exception:
            return self._fail(scope, window, fail_closed)

    @staticmethod
    def _result(count: int, limit: int, window: int, now: int) -> RateResult:
        if count <= limit:
            return RateResult(allowed=True, remaining=max(0, limit - count))
        return RateResult(allowed=False, retry_after=window - (now % window), remaining=0)

    def _fail(self, scope: str, window: int, fail_closed: bool) -> RateResult:
        # availability over throttling — fail open (or closed on request), loudly.
        self._counters.inc(RATE_LIMIT_FAIL_OPEN)
        log.warning("ratelimit.redis_unavailable", scope=scope, fail_closed=fail_closed)
        if fail_closed:
            return RateResult(allowed=False, retry_after=window)
        return RateResult(allowed=True)
