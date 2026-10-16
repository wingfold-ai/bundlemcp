"""The MCP log levels, least to most severe."""

LOG_LEVELS = ("debug", "info", "notice", "warning", "error", "critical", "alert", "emergency")


def at_least(level: str, minimum: str) -> bool:
    """Whether a message at ``level`` clears the ``minimum`` a client asked for."""
    return LOG_LEVELS.index(level) >= LOG_LEVELS.index(minimum)
