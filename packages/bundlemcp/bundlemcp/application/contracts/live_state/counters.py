from typing import Protocol, runtime_checkable

# The metric names the gateway records, so every sink and every reader agree on them.
RATE_LIMIT_REJECTIONS = "rate_limit_rejections"
RATE_LIMIT_FAIL_OPEN = "rate_limit_fail_open"
AUTH_FAILURES = "auth_failures"
AUTH_FAILURE_LOCKOUTS = "auth_failure_lockouts"


@runtime_checkable
class Counters(Protocol):
    """A sink for monotonically increasing counts."""

    def inc(self, name: str, amount: int = 1) -> None: ...

    def get(self, name: str) -> int: ...

    def snapshot(self) -> dict[str, int]:
        """Every counter and its current value."""
        ...
