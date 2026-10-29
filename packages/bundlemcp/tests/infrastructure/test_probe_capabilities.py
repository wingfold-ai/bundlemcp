"""The capabilities snapshot the probe builds from the MCP SDK's own object (UPS-22)."""

import mcp.types
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.server_capabilities import ServerCapabilities
from bundlemcp.infrastructure.fastmcp.connect_mode import connect_mode
from bundlemcp.infrastructure.fastmcp.upstream_probe import FastMcpUpstreamProbe
from fastmcp import Client, FastMCP


def test_ups22_an_sdk_dump_round_trips_with_experimental_keys():
    """UPS-22: the SDK's capabilities, dumped as the probe dumps them, serialise back as stored."""
    sdk = mcp.types.ServerCapabilities(
        experimental={"acme/streaming": {"chunked": True}},
        logging=mcp.types.LoggingCapability(),
        prompts=mcp.types.PromptsCapability(listChanged=False),
        resources=mcp.types.ResourcesCapability(subscribe=True, listChanged=True),
        tools=mcp.types.ToolsCapability(listChanged=True),
        completions=mcp.types.CompletionsCapability(),
    )
    stored = sdk.model_dump(mode="json", by_alias=True, exclude_none=True)

    capabilities = ServerCapabilities.model_validate(stored)

    assert capabilities.model_dump() == stored
    assert list(capabilities.model_dump()) == list(stored)
    assert capabilities.tools_list_changed and capabilities.accepts_resource_subscriptions


async def test_ups22_the_probe_never_stores_null():
    """UPS-22: what the probe hands discovery holds no null member at any depth."""
    upstream = FastMCP("caps")

    @upstream.tool
    def t(x: str) -> str:
        return x

    @upstream.resource("res://a")
    def r() -> str:
        return "a"

    def factory(server, extra_headers, *, observer=None):
        return Client(upstream, mode=connect_mode(server.protocol_mode))

    probe = FastMcpUpstreamProbe(factory)
    result = await probe.probe(McpServer(name="caps", url="http://caps/mcp"), {})

    assert result.capabilities is not None
    dumped = result.capabilities.model_dump()
    assert dumped and _no_null(dumped)
    assert "tools" in dumped and "resources" in dumped


def _no_null(value: object) -> bool:
    if isinstance(value, dict):
        return all(item is not None and _no_null(item) for item in value.values())
    return True
