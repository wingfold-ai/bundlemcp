from pydantic import BaseModel, Field

from bundlemcp.application.contracts.live_state.live_log_entry import LiveLogEntry

SEVERITY = ("debug", "info", "warning", "error", "critical")


class LiveLogFilter(BaseModel):
    """Which live log entries a viewer wants; every field left empty matches everything."""

    level: str | None = Field(
        default=None,
        pattern=r"^(debug|info|warning|error|critical)$",
        description="Lowest severity shown: 'debug', 'info', 'warning', 'error' or 'critical'",
    )
    text: str | None = Field(
        default=None,
        max_length=200,
        description="Shown only when the event name or any field contains this text, any case",
    )
    upstream: str | None = Field(default=None, description="Only events about this upstream")
    endpoint: str | None = Field(default=None, description="Only events about this endpoint")

    def matches(self, entry: LiveLogEntry) -> bool:
        if self.level is not None:
            severity = entry.level.lower()
            if severity in SEVERITY and SEVERITY.index(severity) < SEVERITY.index(self.level):
                return False
        if self.upstream is not None and entry.upstream != self.upstream:
            return False
        if self.endpoint is not None and entry.endpoint != self.endpoint:
            return False
        if self.text:
            needle = self.text.lower()
            haystack = f"{entry.event} {entry.logger or ''} {entry.fields}".lower()
            if needle not in haystack:
                return False
        return True
