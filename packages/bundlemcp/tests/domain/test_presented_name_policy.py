"""Presented-name uniqueness within a bundle (BND-14)."""

import uuid

from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.domain.bundles.presented_name_claims import PresentedNameClaims
from bundlemcp.domain.bundles.presented_name_policy import PresentedNamePolicy
from bundlemcp.domain.bundles.presented_tool import PresentedTool
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.tool import Tool

BUNDLE = uuid.uuid4()
WEATHER = McpServer(name="weather", url="http://weather/mcp")
NOTES = McpServer(name="notes", url="http://notes/mcp")
FORECAST = Tool(server_id=WEATHER.id, name="forecast", schema_hash="h")
WRITE = Tool(server_id=NOTES.id, name="write", schema_hash="h")


def _policy(*curations: BundleTool) -> PresentedNamePolicy:
    return PresentedNamePolicy(
        servers={WEATHER.id: WEATHER, NOTES.id: NOTES},
        tools=[FORECAST, WRITE],
        curations={c.tool_id: c for c in curations},
    )


def test_bnd14_override_equal_to_prefixed_name_collides():
    """BND-14: an override equal to another tool's prefixed name is a collision naming both."""
    clash = BundleTool(bundle_id=BUNDLE, tool_id=WRITE.id, override_name="weather__forecast")
    [collision] = _policy(clash).collisions({WRITE.id})
    assert collision.name == "weather__forecast"
    assert set(collision.holders) == {"weather/forecast", "notes/write"}


def test_bnd14_collisions_not_involving_the_write_are_ignored():
    """BND-14: a check is about the tools a write touches, not older collisions."""
    clash = BundleTool(bundle_id=BUNDLE, tool_id=WRITE.id, override_name="weather__forecast")
    assert _policy(clash).collisions({uuid.uuid4()}) == []


def test_bnd14_discovered_collision_keeps_the_override():
    """BND-14: when two served tools present one name, the overridden one keeps it."""
    curation = BundleTool(bundle_id=BUNDLE, tool_id=WRITE.id, override_name="weather__forecast")

    def presented(server: McpServer, tool: Tool) -> PresentedTool:
        return PresentedTool(
            presented_name="weather__forecast",
            server=server,
            tool=tool,
            title=None,
            description=None,
            input_schema={},
            annotations=None,
        )

    claims = PresentedNameClaims.settle(
        [presented(WEATHER, FORECAST), presented(NOTES, WRITE)], {WRITE.id: curation}
    )
    assert [t.tool.name for t in claims.kept] == ["write"]
    assert [t.tool.name for t in claims.displaced] == ["forecast"]
