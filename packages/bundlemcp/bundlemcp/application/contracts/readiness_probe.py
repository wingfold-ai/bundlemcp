from typing import Protocol, runtime_checkable


@runtime_checkable
class ReadinessProbe(Protocol):
    """Whether the stores this replica depends on can be reached right now."""

    async def check(self) -> None:
        """Return when every store answered; raise when one did not."""
        ...
