"""The current time, behind a contract so a service can be run against a pinned one."""

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable


def utcnow() -> datetime:
    return datetime.now(UTC)


@runtime_checkable
class Clock(Protocol):
    """Where a service reads the time; entities take the instant as an argument instead."""

    def now(self) -> datetime: ...


class SystemClock:
    """The wall clock, in UTC."""

    def now(self) -> datetime:
        return utcnow()
