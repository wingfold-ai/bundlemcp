from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.live_state.rate_result import RateResult


@runtime_checkable
class RateLimiter(Protocol):
    """Fixed-window counters shared by every replica."""

    async def check(
        self, scope: str, limit: int, window: int, *, fail_closed: bool = False
    ) -> RateResult:
        """Count one event in the scope's current window and report whether it fit."""
        ...

    async def peek(
        self, scope: str, limit: int, window: int, *, fail_closed: bool = False
    ) -> RateResult:
        """Report the scope's standing in the current window without counting anything."""
        ...
