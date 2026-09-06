"""Redis accessors: sessions, rate limits, live logs, pub/sub live here.

Key layout is centralized in this module so the live-state footprint stays
auditable (no ad-hoc keys sprinkled through the codebase).
"""

from redis.asyncio import Redis

# Key/channel layout
SESSION_KEY = "bmcp:session:{session_id}"  # SES-1 session record (JSON)
INVALIDATION_CHANNEL = "bmcp:invalidate"  # STP-1 config invalidation events
SIGNAL_CHANNEL = "bmcp:signal:{routing_key}"  # SES-13 cross-replica delivery
LIVE_LOG_STREAM = "bmcp:livelogs"  # LOG-1 ring buffer (XADD MAXLEN)
RATE_KEY = "bmcp:rate:{endpoint}:{scope}"  # RATE-2 counters
CLIENT_METADATA_KEY = "bmcp:cimd:{digest}"  # OAS-13 cached client metadata documents


def create_redis(redis_url: str) -> Redis:
    return Redis.from_url(redis_url, decode_responses=True)
