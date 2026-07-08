"""Shared constants and logger for Redis-backed rate limiting."""

import structlog

log = structlog.get_logger("bundlemcp.gateway.ratelimit")

# key layout: bmcp:rate:{scope}:{bucket}
RATE_KEY = "bmcp:rate:{scope}:{bucket}"
