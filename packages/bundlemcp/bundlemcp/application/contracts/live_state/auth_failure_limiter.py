from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.live_state.rate_result import RateResult


@runtime_checkable
class AuthFailureLimiter(Protocol):
    """Credential-scan protection keyed by client IP, shared by every replica."""

    async def locked_out(self, client_ip: str) -> RateResult:
        """Whether this IP has already exhausted its budget, without counting anything."""
        ...

    async def record_failure(self, client_ip: str) -> RateResult:
        """Count one auth failure for this IP and report whether it is now locked out."""
        ...
