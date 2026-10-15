"""Reconciling a probe with the tool cache (UPS-18, UPS-19)."""

import uuid
from datetime import UTC, datetime

from bundlemcp.domain.servers.probed_tool import ProbedTool
from bundlemcp.domain.servers.tool import Tool
from bundlemcp.domain.servers.tool_sync import sync_tools

SERVER = uuid.uuid4()
FIRST = datetime(2026, 10, 1, tzinfo=UTC)
LATER = datetime(2026, 10, 2, tzinfo=UTC)


def _cache(*names: str) -> dict[str, Tool]:
    staged = sync_tools(SERVER, {}, [ProbedTool(name=n) for n in names], FIRST).staged
    return {tool.name: tool for tool in staged}


def test_ups18_unchanged_run_stages_nothing():
    """UPS-18: a probe that lists exactly what is cached stages no tool and counts no change."""
    cache = _cache("alpha", "beta")
    sync = sync_tools(SERVER, cache, [ProbedTool(name="alpha"), ProbedTool(name="beta")], LATER)
    assert sync.staged == []
    assert sync.changed == 0


def test_ups18_changed_definition_is_staged():
    """UPS-18: a redefined tool is rewritten and counts as one change."""
    cache = _cache("alpha")
    sync = sync_tools(SERVER, cache, [ProbedTool(name="alpha", description="new")], LATER)
    assert [tool.description for tool in sync.staged] == ["new"]
    assert sync.changed == 1


def test_ups19_vanish_and_reappear_are_changes():
    """UPS-18/UPS-19: a tool going stale and coming back each count as a change, and a stale
    tool stays stale, unwritten, on later runs that still miss it."""
    cache = _cache("alpha", "beta")

    vanished = sync_tools(SERVER, cache, [ProbedTool(name="alpha")], LATER)
    assert [(t.name, t.stale_since) for t in vanished.staged] == [("beta", LATER)]
    assert vanished.changed == 1

    still_missing = sync_tools(SERVER, cache, [ProbedTool(name="alpha")], LATER)
    assert still_missing.changed == 0

    back = sync_tools(SERVER, cache, [ProbedTool(name="alpha"), ProbedTool(name="beta")], LATER)
    assert [(t.name, t.is_stale) for t in back.staged] == [("beta", False)]
    assert back.changed == 1
