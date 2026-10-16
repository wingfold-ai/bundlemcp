"""The shared failure streak in Valkey, and how the transport notes a failed connection (UPS-4)."""

import uuid

import httpx2
import pytest
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.infrastructure.fastmcp.response_cap import UpstreamResponseTooLarge
from bundlemcp.infrastructure.fastmcp.transport_failures import RecordedTransportFailures
from bundlemcp.infrastructure.valkey.failure_streak_store import (
    STREAK_KEY,
    STREAK_TTL_SECONDS,
    ValkeyFailureStreak,
)


async def test_ups4_streak_increments_atomically(redis):
    """UPS-4: two replicas' failures add up in one streak, and a reset ends it."""
    server = uuid.uuid4()
    first, second = ValkeyFailureStreak(redis), ValkeyFailureStreak(redis)
    assert await first.record_failure(server) == 1
    assert await second.record_failure(server) == 2
    assert await first.record_failure(server) == 3
    await second.reset(server)
    assert await first.record_failure(server) == 1


async def test_ups4_streak_expires(redis):
    """UPS-4: a streak nobody adds to expires on its own."""
    server = uuid.uuid4()
    await ValkeyFailureStreak(redis).record_failure(server)
    ttl = await redis.ttl(STREAK_KEY.format(server_id=server))
    assert 0 < ttl <= STREAK_TTL_SECONDS


class Raising(httpx2.AsyncBaseTransport):
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        raise self.error


@pytest.mark.parametrize(
    "error",
    [httpx2.ConnectError("refused"), httpx2.ReadError("reset"), ConnectionResetError("reset")],
)
async def test_ups4_a_failed_connection_is_noted_on_the_log(error):
    """UPS-4: the transport records a connection that failed below HTTP."""
    log = ResponseLog()
    transport = RecordedTransportFailures(Raising(error), log)
    with pytest.raises(type(error)):
        await transport.handle_async_request(httpx2.Request("POST", "http://up/mcp"))
    assert log.transport_failed


async def test_ups4_the_gateway_s_own_response_cap_is_not_a_failed_connection():
    """UPS-4: the cap the gateway enforces says nothing about the upstream being down."""
    log = ResponseLog()
    transport = RecordedTransportFailures(Raising(UpstreamResponseTooLarge("big")), log)
    with pytest.raises(UpstreamResponseTooLarge):
        await transport.handle_async_request(httpx2.Request("POST", "http://up/mcp"))
    assert not log.transport_failed
