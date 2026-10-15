from typing import Protocol, runtime_checkable

from bundlemcp.application.metering.paused_invocation import PausedInvocation


@runtime_checkable
class PausedInvocations(Protocol):
    """Metered invocations waiting for client input, shared by every replica.

    A record is claimed at most once: whichever of a later leg, the leg that
    paused it and the expiry sweep claims it first settles the invocation.
    """

    async def pause(self, invocation: PausedInvocation) -> None:
        """Store (or re-arm) the record under the invocation's idempotency key."""
        ...

    async def claim(self, idempotency_key: str) -> PausedInvocation | None:
        """Remove and return the record; None when it is gone or someone claimed it first."""
        ...

    async def expired(self, now: float, limit: int) -> list[str]:
        """Idempotency keys of at most ``limit`` records whose expiry is before ``now``."""
        ...
