"""Rate limiter core tests (EP-17/18/21/22)."""

from bundlemcp.api.http.client_ip import client_ip
from bundlemcp.application.contracts.live_state.counters import (
    AUTH_FAILURE_LOCKOUTS,
    AUTH_FAILURES,
    RATE_LIMIT_FAIL_OPEN,
)
from bundlemcp.infrastructure.config.settings import EnvSettings
from bundlemcp.infrastructure.inprocess.counters import InProcessCounters
from bundlemcp.infrastructure.valkey.auth_failure_limiter import ValkeyAuthFailureLimiter
from bundlemcp.infrastructure.valkey.rate_limiter import ValkeyRateLimiter


async def test_under_limit_allows_then_denies(redis):
    rl = ValkeyRateLimiter(redis)
    # limit 3 per 100s window
    results = [await rl.check("s", 3, 100) for _ in range(4)]
    assert [r.allowed for r in results] == [True, True, True, False]
    assert results[2].remaining == 0
    assert results[3].retry_after > 0  # Retry-After set on denial


async def test_scopes_are_independent(redis):
    rl = ValkeyRateLimiter(redis)
    assert (await rl.check("a", 1, 100)).allowed is True
    assert (await rl.check("a", 1, 100)).allowed is False
    assert (await rl.check("b", 1, 100)).allowed is True  # different scope unaffected


async def test_window_rollover_resets(redis):
    """Crossing into the next fixed window restores the budget."""
    rl = ValkeyRateLimiter(redis)
    assert (await rl.check("w", 1, 100)).allowed is True
    assert (await rl.check("w", 1, 100)).allowed is False  # spent for this window
    redis.advance(100)  # over the bucket edge
    assert (await rl.check("w", 1, 100)).allowed is True
    # a scope that never fired starts fresh regardless of bucket
    assert (await rl.check("w2", 1, 100)).allowed is True


async def test_fail_open_on_redis_error():
    class BoomRedis:
        async def time(self):
            raise ConnectionError("down")

    counters = InProcessCounters()
    rl = ValkeyRateLimiter(BoomRedis(), counters)
    res = await rl.check("s", 1, 100)
    assert res.allowed is True  # fail-open
    assert counters.get(RATE_LIMIT_FAIL_OPEN) == 1


async def test_fail_closed_option():
    class BoomRedis:
        async def time(self):
            raise ConnectionError("down")

    rl = ValkeyRateLimiter(BoomRedis())
    res = await rl.check("s", 1, 100, fail_closed=True)
    assert res.allowed is False


async def test_auth_failure_limiter_locks_out_by_ip(redis):
    """EP-20: threshold reached → lockout; a different IP keeps its own budget."""
    counters = InProcessCounters()
    lim = ValkeyAuthFailureLimiter(redis, limit=2, window=100, counters=counters)
    assert (await lim.record_failure("1.2.3.4")).allowed is True
    assert (await lim.record_failure("1.2.3.4")).allowed is True
    third = await lim.record_failure("1.2.3.4")
    assert third.allowed is False  # locked out
    assert third.retry_after > 0
    assert (await lim.record_failure("5.6.7.8")).allowed is True  # separate IP unaffected
    assert counters.get(AUTH_FAILURES) == 4
    assert counters.get(AUTH_FAILURE_LOCKOUTS) == 1


async def test_auth_failure_limiter_fails_open():
    """EP-21: a Redis outage never locks anyone out."""

    class BoomRedis:
        async def time(self):
            raise ConnectionError("down")

    lim = ValkeyAuthFailureLimiter(BoomRedis(), limit=1, window=100)
    assert (await lim.record_failure("1.2.3.4")).allowed is True
    assert (await lim.record_failure("1.2.3.4")).allowed is True


class _Req:
    def __init__(self, peer, headers=None):
        self.client = type("C", (), {"host": peer})()
        self.headers = headers or {}


def test_client_ip_ignores_xff_from_untrusted_peer():
    settings = EnvSettings(_env_file=None)  # no trusted proxies
    req = _Req("203.0.113.9", {"x-forwarded-for": "1.2.3.4"})
    assert client_ip(req, settings) == "203.0.113.9"


def test_client_ip_honors_xff_from_trusted_proxy():
    settings = EnvSettings(_env_file=None, trusted_proxies=["10.0.0.0/8"])
    req = _Req("10.0.0.5", {"x-forwarded-for": "1.2.3.4, 10.0.0.5"})
    assert client_ip(req, settings) == "1.2.3.4"  # leftmost original client


def test_client_ip_no_client():
    settings = EnvSettings(_env_file=None)
    req = _Req(None) if False else type("R", (), {"client": None, "headers": {}})()
    assert client_ip(req, settings) == "unknown"
