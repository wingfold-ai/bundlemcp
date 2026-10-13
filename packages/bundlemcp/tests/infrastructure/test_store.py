"""Store-layer tests: session records (SES-1/2/3/4, SES-1a) and invalidation (SES-17)."""

import asyncio
import json
import uuid

from bundlemcp.application.contracts.persistence.invalidation_event import InvalidationEvent
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.sessions.session_record import SessionRecord
from bundlemcp.domain.sessions.upstream_binding import UpstreamBinding
from bundlemcp.infrastructure.valkey.publish_invalidation import (
    INVALIDATION_CHANNEL,
    publish_invalidation,
)
from bundlemcp.infrastructure.valkey.session_store import ValkeySessionStore


def _record(session_id: str = "s1") -> SessionRecord:
    return SessionRecord(
        session_id=session_id,
        endpoint_name="ep",
        bundle_name="b",
        identity=CallerIdentity.with_api_key(uuid.uuid4()),
        protocol_version="2025-11-25",
    )


async def test_session_roundtrip_and_delete(redis):
    store = ValkeySessionStore(redis)
    await store.create(_record())

    loaded = await store.load("s1")
    assert loaded is not None
    assert loaded.endpoint_name == "ep"

    await store.delete("s1")
    assert await store.load("s1") is None


async def test_unknown_session_returns_none(redis):
    """SES-3: only genuinely unknown sessions read as missing."""
    store = ValkeySessionStore(redis)
    assert await store.load("nope") is None


async def test_version_mismatch_treated_as_expired(redis):
    """DEP-6: record with an incompatible version reads as expired."""
    store = ValkeySessionStore(redis)
    rec = _record()
    raw = json.loads(rec.model_dump_json())
    raw["version"] = 999
    await redis.set("bmcp:session:s1", json.dumps(raw))
    assert await store.load("s1") is None


async def test_concurrent_binding_updates_do_not_lose_writes(redis):
    """SES-1a: two lazy bindings racing on one record both land."""
    store = ValkeySessionStore(redis)
    await store.create(_record())

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
