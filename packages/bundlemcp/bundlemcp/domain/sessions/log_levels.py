"""The MCP log levels, least to most severe."""

from typing import Literal, get_args

LogLevel = Literal["debug", "info", "notice", "warning", "error", "critical", "alert", "emergency"]

LOG_LEVELS: tuple[LogLevel, ...] = get_args(LogLevel)


def at_least(level: str, minimum: str) -> bool:
    """Whether a message at ``level`` clears the ``minimum`` a client asked for."""
    return LOG_LEVELS.index(level) >= LOG_LEVELS.index(minimum)
