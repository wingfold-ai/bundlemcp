"""Delegated tokens live in Valkey, by hash, until they expire (AUTH-32)."""

import uuid
from datetime import UTC, datetime, timedelta

from bundlemcp.domain.delegation.delegated_token import DelegatedToken
from bundlemcp.infrastructure.valkey.delegated_token_store import (
    DELEGATED_TOKEN_KEY,
    ValkeyDelegatedTokenStore,
)


async def test_auth32_a_record_round_trips_and_expires_with_the_token(redis):
    store = ValkeyDelegatedTokenStore(redis)
    record = DelegatedToken(
        sub="api_key:1",
        server_id=uuid.uuid4(),
        audience="http://seo-gsc:8000/mcp",
        endpoint="main",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    await store.put("h1", record, ttl_seconds=300)
    assert await store.get("h1") == record
    assert 0 < await redis.ttl(DELEGATED_TOKEN_KEY.format(token_hash="h1")) <= 300
    assert await store.get("unknown") is None


async def test_auth32_a_malformed_record_reads_as_absent(redis):
    await redis.set(DELEGATED_TOKEN_KEY.format(token_hash="bad"), "{not json")
    assert await ValkeyDelegatedTokenStore(redis).get("bad") is None
