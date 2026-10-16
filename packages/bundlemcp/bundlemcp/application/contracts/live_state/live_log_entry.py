from typing import Any

from pydantic import BaseModel, Field


class LiveLogEntry(BaseModel):
    """One log event as the live log view shows it: the already-redacted process log line."""

    id: str = Field(
        default="", description="Position in the buffer, assigned when stored; resume after it"
    )
    timestamp: str = Field(description="When the event was logged, ISO 8601")
    level: str = Field(description="Severity: debug, info, warning, error or critical")
    logger: str | None = Field(default=None, description="Logger that wrote the event")
    event: str = Field(description="The event's name or message")
    replica: str = Field(description="The gateway replica that logged it")
    endpoint: str | None = Field(default=None, description="Endpoint the event concerns, if any")
    upstream: str | None = Field(
        default=None, description="Upstream server the event concerns, if any"
    )
    fields: dict[str, Any] = Field(
        default_factory=dict, description="Every other key and value the event carried"
    )
