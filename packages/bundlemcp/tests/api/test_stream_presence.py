"""Which replica holds a notification stream, shared through Valkey (SES-13)."""

from bundlemcp.infrastructure.valkey.stream_presence_store import ValkeyStreamPresence


async def test_ses13_a_hold_another_replica_took_over_is_not_released(redis):
    """SES-13: a client that reconnected elsewhere keeps its new holder."""
    first = ValkeyStreamPresence(redis, hold_seconds=45, replica_id="a")
    second = ValkeyStreamPresence(redis, hold_seconds=45, replica_id="b")
    await first.hold("s1")
    await second.hold("s1")  # the client reconnected its GET stream to replica b
    await first.release("s1")
    assert await second.is_held("s1")
    await second.release("s1")
    assert not await first.is_held("s1")


async def test_ses13_a_hold_expires_unless_refreshed(redis):
    presence = ValkeyStreamPresence(redis, hold_seconds=45)
    await presence.hold("s1")
    assert 0 < await redis.ttl("bmcp:holder:s1") <= 45
