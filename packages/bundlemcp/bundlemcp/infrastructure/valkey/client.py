"""The Valkey client factory.

Key and channel layouts live beside the code that reads and writes them —
``SESSION_KEY`` in the session store, ``INVALIDATION_CHANNEL`` with the
invalidation publisher, ``SIGNAL_CHANNEL`` on the signal bus, ``RATE_KEY`` in
the rate limiter, ``CLIENT_METADATA_KEY`` in the client-metadata fetcher — so
``grep bmcp:`` over the package is the audit of the live-state footprint.
"""

from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialWithJitterBackoff
from redis.exceptions import ConnectionError, TimeoutError

# SES-14: a pooled connection that died with a restarted Valkey is replaced
# inside the same command. Two retries cover the dead connection plus one
# refused connect while the store comes back; the cap keeps a request that
# still fails from stalling.
CONNECTION_RETRIES = 2
RETRY_BACKOFF_BASE_SECONDS = 0.05
RETRY_BACKOFF_CAP_SECONDS = 0.5
# An idle pooled connection is pinged before reuse once it has been idle this long.
HEALTH_CHECK_INTERVAL_SECONDS = 30


def create_redis(redis_url: str) -> Redis:
    backoff = ExponentialWithJitterBackoff(
        base=RETRY_BACKOFF_BASE_SECONDS, cap=RETRY_BACKOFF_CAP_SECONDS
    )
    return Redis.from_url(
        redis_url,
        decode_responses=True,
        retry=Retry(backoff, CONNECTION_RETRIES),
        retry_on_error=[ConnectionError, TimeoutError],
        health_check_interval=HEALTH_CHECK_INTERVAL_SECONDS,
    )
