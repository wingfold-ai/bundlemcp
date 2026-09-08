"""The Valkey client factory.

Key and channel layouts live beside the code that reads and writes them —
``SESSION_KEY`` in the session store, ``INVALIDATION_CHANNEL`` with the
invalidation publisher, ``SIGNAL_CHANNEL`` on the signal bus, ``RATE_KEY`` in
the rate limiter, ``CLIENT_METADATA_KEY`` in the client-metadata fetcher — so
``grep bmcp:`` over the package is the audit of the live-state footprint.
"""

from redis.asyncio import Redis


def create_redis(redis_url: str) -> Redis:
    return Redis.from_url(redis_url, decode_responses=True)
