import asyncio
import json
from typing import Any

import structlog
from redis.asyncio import Redis

from bundlemcp.application.contracts.live_state.stream_registry import StreamRegistry
from bundlemcp.application.serving.signals.cancel_signal import CancelSignal
from bundlemcp.application.serving.signals.deliver_signal import DeliverSignal
from bundlemcp.application.serving.signals.reply_signal import ReplySignal
from bundlemcp.application.serving.signals.resume_signal import ResumeSignal
from bundlemcp.application.serving.signals.signal_envelope import SignalEnvelope

log = structlog.get_logger("bundlemcp.infrastructure.valkey.signal_bus")

SIGNAL_CHANNEL = "bmcp:signal:{routing_key}"  # SES-13 cross-replica delivery
SIGNAL_PATTERN = "bmcp:signal:*"


class ValkeySignalBus:
    def __init__(self, redis: Redis, registry: StreamRegistry) -> None:
        self._redis = redis
        self._registry = registry
        self._task: asyncio.Task | None = None
        self._ready = asyncio.Event()

    # --- publish API ---

    async def cancel(self, routing_key: str, request_id: str) -> None:
        await self._publish(
            routing_key, CancelSignal(routing_key=routing_key, request_id=request_id)
        )

    async def deliver(self, stream_id: str, payload: dict[str, Any]) -> None:
        await self._publish(stream_id, DeliverSignal(stream_id=stream_id, payload=payload))

    async def reply(self, correlation_id: str, payload: dict[str, Any]) -> None:
        await self._publish(
            correlation_id, ReplySignal(correlation_id=correlation_id, payload=payload)
        )

    async def resume(self, correlation_id: str, phase: str, payload: dict[str, Any]) -> None:
        await self._publish(
            correlation_id,
            ResumeSignal(correlation_id=correlation_id, phase=phase, payload=payload),
        )

    async def _publish(self, routing_key: str, signal) -> None:
        channel = SIGNAL_CHANNEL.format(routing_key=routing_key)
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
            self._registry.cancel_local(signal.routing_key, signal.request_id)
        elif isinstance(signal, DeliverSignal):
            self._registry.deliver_local(signal.stream_id, signal.payload)
        elif isinstance(signal, ReplySignal):
            self._registry.reply_local(signal.correlation_id, signal.payload)
        elif isinstance(signal, ResumeSignal):
            self._registry.resume_local(signal.correlation_id, signal.phase, signal.payload)
