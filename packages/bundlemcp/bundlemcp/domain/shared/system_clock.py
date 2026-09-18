"""The clock every deployment runs on."""

from datetime import datetime

from bundlemcp.domain.shared.clock import utcnow


class SystemClock:
    """The wall clock, in UTC."""

    def now(self) -> datetime:
        return utcnow()
