"""Periodic tool refresh (spec 11 DISC-7): one replica sweeps per interval."""

from bundlemcp.api.jobs.tool_refresher import ToolRefresher
from bundlemcp.application.schemas import DiscoverySweep
from bundlemcp.infrastructure.valkey.refresh_lock import ValkeyRefreshLock


class CountingDiscovery:
    def __init__(self) -> None:
        self.sweeps = 0

    async def discover_all(self) -> DiscoverySweep:
        self.sweeps += 1
        return DiscoverySweep(servers=3)


async def test_one_replica_sweeps_per_interval(redis):
    """DISC-7: a second replica finds the interval's lease held and skips its tick."""
    discovery = CountingDiscovery()
    first = ToolRefresher(discovery, ValkeyRefreshLock(redis), interval_seconds=1800)
    second = ToolRefresher(discovery, ValkeyRefreshLock(redis), interval_seconds=1800)

    assert await first.refresh_once() == DiscoverySweep(servers=3)
    assert await second.refresh_once() is None
    assert discovery.sweeps == 1


async def test_lease_expires_before_the_next_tick(redis):
    """DISC-7: the lease is shorter than the interval, so the next tick can sweep again."""
    refresher = ToolRefresher(CountingDiscovery(), ValkeyRefreshLock(redis), interval_seconds=1800)

    await refresher.refresh_once()

    ttl = await redis.ttl("bundlemcp:discovery:sweep")
    assert 0 < ttl < 1800
