"""Redis-backed rate limiting.

Fixed-window counter via atomic INCR + EXPIRE, bucketed by Redis server time
so all replicas share the window. Fails open on Redis trouble unless the
caller asks for fail-closed.
"""

from bundlemcp.gateway.ratelimit.auth_failure_guard import AuthFailureGuard
from bundlemcp.gateway.ratelimit.auth_failure_limiter import AuthFailureLimiter
from bundlemcp.gateway.ratelimit.rate_limiter import RATE_KEY, RateLimiter
from bundlemcp.gateway.ratelimit.rate_result import RateResult

__all__ = [
    "RATE_KEY",
    "AuthFailureGuard",
    "AuthFailureLimiter",
    "RateLimiter",
    "RateResult",
]
