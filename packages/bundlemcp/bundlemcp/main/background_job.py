"""What the composition root starts with the app and stops at shutdown."""

from typing import Protocol


class BackgroundJob(Protocol):
    """A loop that runs beside the requests: started once, stopped once, both synchronously."""

    def start(self) -> None:
        """Begin the loop in the background; returns at once."""
        ...

    def stop(self) -> None:
        """Cancel the loop; called once, at shutdown."""
        ...
