"""Paused invocations in Valkey: stored, claimed once, found when overdue (PROT-26)."""

import asyncio
import time
from datetime import UTC, datetime

import pytest
from bundlemcp.application.metering.meter_context import MeterContext
from bundlemcp.application.metering.paused_invocation import PausedInvocation
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.endpoints.endpoint_profile import EndpointProfile
from bundlemcp.domain.shared.system_clock import SystemClock
from bundlemcp.infrastructure.memory.in_memory_paused_invocations import (
    InMemoryPausedInvocations,
)
from bundlemcp.infrastructure.memory.manual_clock import ManualClock
from bundlemcp.infrastructure.valkey.paused_invocations import (
    EXPIRY_INDEX,
    INVOCATION_KEY,
    SWEEP_GRACE_SECONDS,
    ValkeyPausedInvocations,
)


def _paused(key: str, expires_at: float) -> PausedInvocation:
    return PausedInvocation(
        context=MeterContext(
            sub="api_key:1",
            email=None,
            oidc_issuer=None,
            oidc_sub=None,
            auth_method=EndpointAuthMode.API_KEY,
            endpoint="main",
            profile=EndpointProfile.DEFAULT,
            bundle="main",
            session_id=None,
            server="echo",
            tool="say",
            idempotency_key=key,
            headers={},
            scratch={"reservation": "r-1"},
        ),
        expires_at=expires_at,
    )


@pytest.fixture(params=["valkey", "memory"])
def invocations(request, redis):
    return (
        ValkeyPausedInvocations(redis, clock=SystemClock())
        if request.param == "valkey"
        else InMemoryPausedInvocations()
    )


async def test_prot26_two_concurrent_claims_settle_once(invocations):
    """PROT-26: a later leg and the sweep claiming at one moment get one record between them."""
    await invocations.pause(_paused("k1", time.time() + 60))
    first, second = await asyncio.gather(invocations.claim("k1"), invocations.claim("k1"))
    assert [c is not None for c in (first, second)].count(True) == 1
    claimed = first or second
    assert claimed.context.scratch == {"reservation": "r-1"}


async def test_prot26_only_overdue_records_are_found(invocations):
    """PROT-26: the sweep sees records whose state expired, not ones still waiting."""
    now = time.time()
    await invocations.pause(_paused("overdue", now - 1))
    await invocations.pause(_paused("waiting", now + 60))
    assert await invocations.expired(now, 10) == ["overdue"]
    assert await invocations.claim("overdue") is not None
    assert await invocations.expired(now, 10) == []


async def test_prot26_a_claim_removes_the_record_from_the_expiry_index(redis):
    store = ValkeyPausedInvocations(redis, clock=SystemClock())
    await store.pause(_paused("k1", time.time() - 1))
    assert await store.claim("k1") is not None
    assert await redis.zcard(EXPIRY_INDEX) == 0
    assert await store.claim("k1") is None


async def test_ses16_pause_ttl_follows_the_clock(redis):
    """SES-16: the stored record lives for its expiry measured on the injected clock, plus the
    sweep's grace, wherever the wall clock is."""
    clock = ManualClock(datetime(2026, 10, 1, 9, tzinfo=UTC))
    store = ValkeyPausedInvocations(redis, clock=clock)
    await store.pause(_paused("k1", clock.now().timestamp() + 120))
    assert await redis.ttl(INVOCATION_KEY.format(idempotency_key="k1")) == 120 + SWEEP_GRACE_SECONDS
