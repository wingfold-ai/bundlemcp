import asyncio
import json
from typing import Any

import structlog
from redis.asyncio import Redis

from bundlemcp.gateway.signals.cancel_signal import CancelSignal
from bundlemcp.gateway.signals.deliver_signal import DeliverSignal
from bundlemcp.gateway.signals.reply_signal import ReplySignal
from bundlemcp.gateway.signals.signal_envelope import SignalEnvelope
from bundlemcp.gateway.streams import StreamRegistry
from bundlemcp.store.redis import SIGNAL_CHANNEL

log = structlog.get_logger("bundlemcp.gateway.signals")

SIGNAL_PATTERN = "bmcp:signal:*"


class SignalBus:
    def __init__(self, redis: Redis, registry: StreamRegistry) -> None:
        self._redis = redis
        self._registry = registry
        self._task: asyncio.Task | None = None
        self._ready = asyncio.Event()

    # --- publish API ---

    async def cancel(self, session_id: str, request_id: str) -> None:
        await self._publish(session_id, CancelSignal(session_id=session_id, request_id=request_id))

    async def deliver(self, session_id: str, payload: dict[str, Any]) -> None:
        await self._publish(session_id, DeliverSignal(session_id=session_id, payload=payload))

    async def reply(self, correlation_id: str, payload: dict[str, Any]) -> None:
        await self._publish(
            correlation_id, ReplySignal(correlation_id=correlation_id, payload=payload)
        )

    async def _publish(self, routing_key: str, signal) -> None:
        channel = SIGNAL_CHANNEL.format(session_id=routing_key)
        await self._redis.publish(channel, SignalEnvelope(signal=signal).model_dump_json())

    # --- subscription loop ---

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())
        await self._ready.wait()  # subscribed before serving (no lost signals at boot)

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
                await pubsub.psubscribe(SIGNAL_PATTERN)
                self._ready.set()
                async for message in pubsub.listen():
                    if message.get("type") != "pmessage":
                        continue
                    try:
                        envelope = SignalEnvelope(**json.loads(message["data"]))
                    except (ValueError, TypeError):
                        log.warning("signals.bad_message")
                        continue
                    self._dispatch(envelope.signal)
            except asyncio.CancelledError:
                raise
            except Exception:
                self._ready.clear()
                log.warning("signals.subscription_lost", exc_info=True)
                await asyncio.sleep(1.0)

    def _dispatch(self, signal) -> None:
        if isinstance(signal, CancelSignal):
            self._registry.cancel_local(signal.session_id, signal.request_id)
        elif isinstance(signal, DeliverSignal):
            self._registry.deliver_local(signal.session_id, signal.payload)
        elif isinstance(signal, ReplySignal):
            self._registry.reply_local(signal.correlation_id, signal.payload)
