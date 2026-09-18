from datetime import datetime, timedelta


class ManualClock:
    """A clock that only moves when a test moves it."""

    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta
