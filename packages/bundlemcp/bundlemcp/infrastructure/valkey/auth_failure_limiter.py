import structlog
from redis.asyncio import Redis

from bundlemcp.application.contracts.live_state.rate_result import RateResult
from bundlemcp.application.contracts.observability.gateway_metrics import GatewayMetrics
from bundlemcp.infrastructure.valkey.rate_limiter import ValkeyRateLimiter

log = structlog.get_logger(__name__)


class ValkeyAuthFailureLimiter:
    """Gateway-wide credential-scan protection, keyed by client IP.

    Each authentication failure increments a per-IP fixed-window counter; once
    the configured threshold is exceeded the IP is locked out until the window
    rolls over. Always fails open on Redis trouble — availability beats lockout
    — and says so with an alarm of its own, distinct from the traffic limiter's.
    """

    def __init__(self, redis: Redis, *, limit: int, window: int, metrics: GatewayMetrics) -> None:
        self._metrics = metrics
        self._limiter = ValkeyRateLimiter(redis, on_fail_open=self._failed_open)
        self._limit = limit
        self._window = window

    def _failed_open(self) -> None:
        self._metrics.auth_limiter_failed_open()
        log.warning("auth_failure_limiter.failed_open")

    async def locked_out(self, client_ip: str) -> RateResult:
        """Whether this IP has already exhausted its budget, without counting anything."""
        return await self._limiter.peek(f"authfail:{client_ip}", self._limit, self._window)

    async def record_failure(self, client_ip: str) -> RateResult:
        """Count one auth failure for this IP and report whether it is now locked out."""
        self._metrics.auth_failed()
        result = await self._limiter.check(f"authfail:{client_ip}", self._limit, self._window)
        if not result.allowed:
            self._metrics.auth_locked_out()
        return result
