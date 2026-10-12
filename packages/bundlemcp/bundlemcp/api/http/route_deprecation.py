"""When a renamed route's old path stops answering, and the headers that announce it."""

from datetime import UTC, date, datetime, time
from email.utils import format_datetime

from pydantic import BaseModel, ConfigDict, Field


class RouteDeprecation(BaseModel):
    """The deprecation window of a set of renamed routes.

    The old paths answer exactly like the new ones until ``sunset_on``, and
    every response from them says so in standard headers; after it they answer
    410 Gone with the new path.
    """

    model_config = ConfigDict(frozen=True)

    deprecated_on: date = Field(
        description="The day the new path shipped and the old one was deprecated"
    )
    sunset_on: date = Field(description="The first day the old path no longer answers")

    def is_sunset(self, now: datetime) -> bool:
        return now.date() >= self.sunset_on

    def headers(self, successor: str) -> list[tuple[str, str]]:
        """The Deprecation, Sunset and Link headers for a response from an old path."""
        deprecated_at = datetime.combine(self.deprecated_on, time(), tzinfo=UTC)
        sunset_at = datetime.combine(self.sunset_on, time(), tzinfo=UTC)
        return [
            ("Deprecation", f"@{int(deprecated_at.timestamp())}"),  # RFC 9745 date
            ("Sunset", format_datetime(sunset_at, usegmt=True)),  # RFC 8594 HTTP-date
            ("Link", f'<{successor}>; rel="successor-version"'),
        ]
