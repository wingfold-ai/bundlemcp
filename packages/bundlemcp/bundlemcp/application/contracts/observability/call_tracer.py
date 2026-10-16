from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable


@runtime_checkable
class TracedSpan(Protocol):
    """One span while it is open; attributes are identifiers and outcomes, never secrets."""

    def set_attribute(self, key: str, value: str) -> None: ...


@runtime_checkable
class CallTracer(Protocol):
    """Where the span of each upstream tool call goes; the default records nothing."""

    def span(self, name: str, attributes: dict[str, str]) -> AbstractContextManager[TracedSpan]:
        """Open a span for the block, a child of the current one when there is one."""
        ...
