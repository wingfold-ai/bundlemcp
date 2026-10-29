"""Store-layer tests: session records (SES-1/2/3/4, SES-1a) and invalidation (SES-17)."""

import asyncio
import json
import uuid

from bundlemcp.application.contracts.persistence.invalidation_event import InvalidationEvent
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.sessions.session_lifetime import SessionLifetime
from bundlemcp.domain.sessions.session_record import SessionRecord
from bundlemcp.domain.sessions.upstream_binding import UpstreamBinding
from bundlemcp.domain.shared.system_clock import SystemClock
from bundlemcp.infrastructure.valkey.publish_invalidation import (
    INVALIDATION_CHANNEL,
    publish_invalidation,
)
from bundlemcp.infrastructure.valkey.session_store import ValkeySessionStore

DAY = SessionLifetime(seconds=86400)


def _record(session_id: str = "s1") -> SessionRecord:
    return SessionRecord(
        session_id=session_id,
        endpoint_name="ep",
        bundle_name="b",
        identity=CallerIdentity.with_api_key(uuid.uuid4()),
        protocol_version="2025-11-25",
    )


async def test_session_roundtrip_and_delete(redis):
    store = ValkeySessionStore(redis, clock=SystemClock())
    await store.create(_record(), DAY)

    loaded = await store.load("s1")
    assert loaded is not None
    assert loaded.endpoint_name == "ep"

    await store.delete("s1")
    assert await store.load("s1") is None


async def test_unknown_session_returns_none(redis):
    """SES-3: only genuinely unknown sessions read as missing."""
    store = ValkeySessionStore(redis, clock=SystemClock())
    assert await store.load("nope") is None


async def test_version_mismatch_treated_as_expired(redis):
    """DEP-6: record with an incompatible version reads as expired."""
    store = ValkeySessionStore(redis, clock=SystemClock())
    rec = _record()
    raw = json.loads(rec.model_dump_json())
    raw["version"] = 999
    await redis.set("bmcp:session:s1", json.dumps(raw))
    assert await store.load("s1") is None


async def test_concurrent_binding_updates_do_not_lose_writes(redis):
    """SES-1a: two lazy bindings racing on one record both land."""
    store = ValkeySessionStore(redis, clock=SystemClock())
    await store.create(_record(), DAY)

    async def bind(server: str):
        binding = UpstreamBinding(server_name=server, upstream_session_id=server)
        await store.set_binding("s1", binding)

    await asyncio.gather(bind("srv-a"), bind("srv-b"))
    loaded = await store.load("s1")
    assert loaded is not None
    assert set(loaded.bindings) == {"srv-a", "srv-b"}


async def test_invalidation_publish(redis):
    pubsub = redis.pubsub()
    await pubsub.subscribe(INVALIDATION_CHANNEL)
    await publish_invalidation(
        redis, InvalidationEvent(entity_type="api_key", key="k1", action="deleted")
    )
    # first message is the subscribe confirmation
    msg = None
    for _ in range(10):
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
        if msg:
            break
    assert msg is not None
    event = InvalidationEvent(**json.loads(msg["data"]))
    assert event.entity_type == "api_key"
    assert event.action == "deleted"


async def test_ses1_dep6_a_record_without_timestamps_still_loads_at_version_2(redis):
    """SES-1, DEP-6: a record of the previous build, written without timestamps, still loads."""
    raw = json.loads(_record().model_dump_json())
    del raw["created_at"], raw["last_active_at"]
    await redis.set("bmcp:session:s1", json.dumps(raw))
    loaded = await ValkeySessionStore(redis, clock=SystemClock()).load("s1")
    assert loaded is not None and loaded.version == 2


async def test_ses1_ses10_ttl_follows_the_lifetime(redis):
    """SES-1, SES-10: the TTL is the lifetime plus the sweeper's margin; 0 stores no TTL."""
    store = ValkeySessionStore(redis, clock=SystemClock())
    hour = SessionLifetime(seconds=3600)
    await store.create(_record(), hour)
    assert await redis.ttl("bmcp:session:s1") == hour.store_ttl
    assert await redis.zscore("bmcp:sessions:active", "s1") is not None

    await store.create(_record("s2"), SessionLifetime(seconds=0))
    assert await redis.ttl("bmcp:session:s2") == -1  # no expiry
    assert await redis.zscore("bmcp:sessions:active", "s2") is None


async def test_ses10_a_changed_lifetime_applies_at_the_next_touch(redis):
    """SES-10: touch records the activity and sets the TTL from the lifetime it is given."""
    store = ValkeySessionStore(redis, clock=SystemClock())
    await store.create(_record(), DAY)
    before = await store.load("s1")
    assert before is not None
    await asyncio.sleep(0.01)
    await store.touch("s1", SessionLifetime(seconds=600))
    after = await store.load("s1")
    assert after is not None and after.last_active_at > before.last_active_at
    assert await redis.ttl("bmcp:session:s1") == SessionLifetime(seconds=600).store_ttl
    await store.touch("s1", SessionLifetime(seconds=0))
    assert await redis.ttl("bmcp:session:s1") == -1


async def test_ses1_a_binding_update_keeps_the_ttl(redis):
    """SES-1: an update that is not activity leaves the record's TTL alone."""
    store = ValkeySessionStore(redis, clock=SystemClock())
    hour = SessionLifetime(seconds=3600)
    await store.create(_record(), hour)
    await redis.expire("bmcp:session:s1", 500)
    await store.set_binding("s1", UpstreamBinding(server_name="echo", identity_key="k"))
    assert 0 < await redis.ttl("bmcp:session:s1") <= 500


async def test_ses10_delete_leaves_the_activity_index(redis):
    store = ValkeySessionStore(redis, clock=SystemClock())
    await store.create(_record(), DAY)
    await store.delete("s1")
    assert await redis.zscore("bmcp:sessions:active", "s1") is None
