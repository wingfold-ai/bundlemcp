from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class MetricsPage(BaseModel):
    """One scrape's worth of metrics, ready to send."""

    content: bytes = Field(description="The metrics in the exposition format")
    media_type: str = Field(description="The content type that format is served with")


@runtime_checkable
class MetricsExposition(Protocol):
    """What a scrape of this replica returns."""

    async def render(self) -> MetricsPage:
        """Read the gauges that are sampled at scrape time, then render everything."""
        ...
