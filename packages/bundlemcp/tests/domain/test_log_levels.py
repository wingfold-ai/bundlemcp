"""The MCP log levels and their order."""

from typing import get_args

from bundlemcp.domain.sessions.log_levels import LOG_LEVELS, LogLevel, at_least


def test_prot7_log_levels_run_from_least_to_most_severe():
    """PROT-7: the eight MCP levels, in the order a minimum is compared against."""
    assert LOG_LEVELS == (
        "debug",
        "info",
        "notice",
        "warning",
        "error",
        "critical",
        "alert",
        "emergency",
    )
    assert LOG_LEVELS == get_args(LogLevel)


def test_prot7_a_level_clears_a_minimum_at_or_below_it():
    """PROT-7: a message is delivered at or above the level the client asked for."""
    assert at_least("error", "warning")
    assert at_least("warning", "warning")
    assert not at_least("info", "warning")
