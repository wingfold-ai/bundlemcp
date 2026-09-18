"""Where new secrets come from, behind a contract so a test can make them predictable."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class SecretGenerator(Protocol):
    def token(self, nbytes: int) -> str:
        """A fresh URL-safe secret with this many bytes of entropy."""
        ...
