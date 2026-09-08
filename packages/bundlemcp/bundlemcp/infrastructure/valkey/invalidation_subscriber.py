import asyncio
from collections.abc import Awaitable, Callable

import structlog
from pydantic import ValidationError
from redis.asyncio import Redis

from bundlemcp.application.contracts.persistence.invalidation_event import InvalidationEvent
from bundlemcp.infrastructure.valkey.publish_invalidation import INVALIDATION_CHANNEL

log = structlog.get_logger(__name__)


class InvalidationSubscriber:
    """Runs a pub/sub loop and fans events out to registered callbacks."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._callbacks: list[Callable[[InvalidationEvent], Awaitable[None]]] = []
        self._flush_callbacks: list[Callable[[], Awaitable[None]]] = []
        self._task: asyncio.Task[None] | None = None

    def on_event(self, callback: Callable[[InvalidationEvent], Awaitable[None]]) -> None:
        self._callbacks.append(callback)

    def on_reconnect_flush(self, callback: Callable[[], Awaitable[None]]) -> None:
        """After a subscription gap all config caches must be flushed."""
        self._flush_callbacks.append(callback)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while True:
            try:
                pubsub = self._redis.pubsub()
                await pubsub.subscribe(INVALIDATION_CHANNEL)
                for cb in self._flush_callbacks:
                    await cb()
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    try:
                        event = InvalidationEvent.model_validate_json(message["data"])
                    except ValidationError:
                        log.warning("invalidation.bad_event")
                        continue
                    for cb in self._callbacks:
                        await cb(event)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning("invalidation.subscription_lost", exc_info=True)
                await asyncio.sleep(1.0)
