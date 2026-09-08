"""Signal bus and stream registry tests (SES-13): exactly-once delivery, cross-replica routing."""

import asyncio

from bundlemcp.application.serving.stream_key import StreamKey
from bundlemcp.infrastructure.inprocess.stream_registry import InProcessStreamRegistry
from bundlemcp.infrastructure.valkey.signal_bus import ValkeySignalBus
from fakeredis.aioredis import FakeRedis

BusPair = tuple[ValkeySignalBus, InProcessStreamRegistry, ValkeySignalBus, InProcessStreamRegistry]

S1 = StreamKey(endpoint_name="main", bundle_name="main", stream_id="s1")


async def _bus_pair(redis: FakeRedis) -> BusPair:
    """Two 'replicas' sharing one Redis."""
    reg_a, reg_b = InProcessStreamRegistry(), InProcessStreamRegistry()
    bus_a, bus_b = ValkeySignalBus(redis, reg_a), ValkeySignalBus(redis, reg_b)
    await bus_a.start()
    await bus_b.start()
    return bus_a, reg_a, bus_b, reg_b


async def test_deliver_reaches_owning_replica_exactly_once(redis):
    bus_a, reg_a, bus_b, reg_b = _b = await _bus_pair(redis)
    try:
        queue = reg_b.register_stream(S1)  # stream lives on replica B
        await bus_a.deliver("s1", {"method": "notifications/tools/list_changed"})

        payload = await asyncio.wait_for(queue.get(), timeout=2)
        assert payload["method"] == "notifications/tools/list_changed"
        # exactly once: nothing further queued
        await asyncio.sleep(0.1)
        assert queue.empty()
    finally:
        await bus_a.stop()
        await bus_b.stop()


async def test_publisher_own_stream_receives_once(redis):
    """Publish-only design: the publishing replica's own stream gets one copy."""
    bus_a, reg_a, bus_b, reg_b = await _bus_pair(redis)
    try:
        queue = reg_a.register_stream(S1)
        await bus_a.deliver("s1", {"method": "ping"})
        await asyncio.wait_for(queue.get(), timeout=2)
        await asyncio.sleep(0.1)
        assert queue.empty()
    finally:
        await bus_a.stop()
        await bus_b.stop()


async def test_cancel_routed_cross_replica(redis):
    """PROT-3: cancel arriving at replica A reaches the call held on replica B."""
    bus_a, reg_a, bus_b, reg_b = await _bus_pair(redis)
    try:
        handle = reg_b.register_call("s1", "req-42")
        await bus_a.cancel("s1", "req-42")
        await asyncio.wait_for(handle.cancel_event.wait(), timeout=2)
    finally:
        await bus_a.stop()
        await bus_b.stop()


async def test_reply_resolves_future_cross_replica(redis):
    """PROT-4: client's response on replica A resolves the future on replica B."""
    bus_a, reg_a, bus_b, reg_b = await _bus_pair(redis)
    try:
        future = reg_b.register_reply("corr-1")
        await bus_a.reply("corr-1", {"result": {"answer": 42}})
        payload = await asyncio.wait_for(future, timeout=2)
        assert payload["result"]["answer"] == 42

        # double reply is ignored (future already done)
        await bus_a.reply("corr-1", {"result": {"answer": 99}})
        await asyncio.sleep(0.1)
        assert future.result()["result"]["answer"] == 42
    finally:
        await bus_a.stop()
        await bus_b.stop()


async def test_unregistered_targets_ignored(redis):
    """Signals for objects nobody holds are dropped silently."""
    bus_a, reg_a, bus_b, reg_b = await _bus_pair(redis)
    try:
        await bus_a.deliver("ghost", {"method": "x"})
        await bus_a.cancel("ghost", "r")
        await bus_a.reply("ghost", {})
        await asyncio.sleep(0.1)  # nothing raises, nothing leaks
    finally:
        await bus_a.stop()
        await bus_b.stop()
