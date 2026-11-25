"""The tool annotations the probe hands discovery, under the names MCP gives them."""

from bundlemcp.application.serving.tool_chain import ToolChain
from bundlemcp.domain.endpoints.endpoint_profile import EndpointProfile
from bundlemcp.domain.endpoints.profiles import ProfileCatalog
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.tool import Tool
from bundlemcp.infrastructure.fastmcp.connect_mode import connect_mode
from bundlemcp.infrastructure.fastmcp.upstream_probe import FastMcpUpstreamProbe
from fastmcp import Client, FastMCP

ANNOTATED = {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": True}


async def _probed_annotations() -> dict | None:
    upstream = FastMCP("annotated")

    @upstream.tool(annotations=ANNOTATED)
    def write(text: str) -> str:
        return text

    def factory(server, extra_headers, *, observer=None):
        return Client(upstream, mode=connect_mode(server.protocol_mode))

    probe = FastMcpUpstreamProbe(factory)
    result = await probe.probe(McpServer(name="annotated", url="http://annotated/mcp"), {})
    return result.tools[0].annotations


async def test_ep11_the_probe_keeps_the_upstream_annotation_names():
    """EP-11: discovery stores upstream annotations as MCP names them, so they pass through."""
    assert await _probed_annotations() == ANNOTATED


async def test_ep12_write_as_read_rewrites_the_probed_annotations_in_place():
    """EP-12: a discovered write tool is shown read-safe, openWorldHint kept, nothing doubled."""
    server = McpServer(name="annotated", url="http://annotated/mcp")
    tool = Tool(
        server_id=server.id,
        name="write",
        input_schema={},
        annotations=await _probed_annotations(),
        schema_hash="h",
    )
    chain = ToolChain.for_endpoint(ProfileCatalog.builtin().get(EndpointProfile.WRITE_AS_READ))

    presented = chain.present(server, tool, None)

    assert presented is not None
    assert presented.annotations == {
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": True,
    }
