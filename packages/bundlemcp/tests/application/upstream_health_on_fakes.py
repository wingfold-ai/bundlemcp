"""An upstream health reporter on the in-memory fakes, for tests that build discovery."""

from bundlemcp.application.discovery.upstream_health import UpstreamHealth
from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.infrastructure.memory.in_memory_failure_streak import InMemoryFailureStreak
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
    InMemoryUnitOfWorkFactory,
)


def health_on(
    uow: InMemoryUnitOfWork, streak: InMemoryFailureStreak | None = None
) -> UpstreamHealth:
    """A reporter over ``uow``; pass one ``streak`` to several to stand in for replicas."""
    units = InMemoryUnitOfWorkFactory(uow)
    return UpstreamHealth(units, streak or InMemoryFailureStreak(), RuntimeConfig(units))
