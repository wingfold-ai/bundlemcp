"""Metered invocations waiting for client input, kept in Valkey until they end or expire."""

import time

import structlog
from pydantic import ValidationError
from redis.asyncio import Redis

from bundlemcp.application.metering.paused_invocation import PausedInvocation

log = structlog.get_logger(__name__)

INVOCATION_KEY = "bmcp:invocation:{idempotency_key}"
# idempotency keys scored by their expiry, so the sweep finds the overdue ones
EXPIRY_INDEX = "bmcp:invocations:expiry"
# the record outlives its expiry by this much, so the sweep still finds it
SWEEP_GRACE_SECONDS = 600


class ValkeyPausedInvocations:
    """One record per paused invocation; GETDEL makes every claim atomic across replicas."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def pause(self, invocation: PausedInvocation) -> None:
        key = invocation.context.idempotency_key
        # expires_at is this gateway's wall-clock time, like the requestState's
        ttl = max(1, int(invocation.expires_at - time.time()) + SWEEP_GRACE_SECONDS)
        async with self._redis.pipeline(transaction=True) as tx:
            tx.set(INVOCATION_KEY.format(idempotency_key=key), invocation.model_dump_json(), ex=ttl)
            tx.zadd(EXPIRY_INDEX, {key: invocation.expires_at})
            await tx.execute()

    async def claim(self, idempotency_key: str) -> PausedInvocation | None:
        raw = await self._redis.getdel(INVOCATION_KEY.format(idempotency_key=idempotency_key))
        await self._redis.zrem(EXPIRY_INDEX, idempotency_key)
        if raw is None:
            return None
        try:
            return PausedInvocation.model_validate_json(raw)
        except ValidationError:
            log.warning("paused_invocation.malformed")
            return None

    async def expired(self, now: float, limit: int) -> list[str]:
        return list(await self._redis.zrangebyscore(EXPIRY_INDEX, "-inf", now, start=0, num=limit))
