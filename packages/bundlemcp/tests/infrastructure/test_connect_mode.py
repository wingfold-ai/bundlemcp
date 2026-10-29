"""A server's protocol mode reaches the MCP client in the client library's words (UPS-10)."""

from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.protocol_mode import NegotiationMode
from bundlemcp.infrastructure.fastmcp.client_factory import default_client_factory
from bundlemcp.infrastructure.fastmcp.connect_mode import connect_mode
from fastmcp import FastMCP

from tests.conftest import hermetic_settings
from tests.loopback_upstream import RecordingUpstream, serving_upstream


def _upstream() -> FastMCP:
    server = FastMCP("echo")

    @server.tool
    def echo(text: str) -> str:
        return f"echo:{text}"

    return server


def test_ups10_modes_translate_to_the_client_library():
    """UPS-10: 'session' is the client's 'legacy', and 'auto' and a revision pass unchanged."""
    assert connect_mode(NegotiationMode.SESSION) == "legacy"
    assert connect_mode(NegotiationMode.AUTO) == "auto"
    assert connect_mode("2026-07-28") == "2026-07-28"


async def test_ups10_session_mode_connects_through_the_handshake():
    """UPS-10: a server in session mode is reached through the initialize handshake, without
    first probing server/discover."""
    recording = RecordingUpstream(_upstream())
    factory = default_client_factory(
        hermetic_settings(egress_allow_cidrs=["127.0.0.1/32"]), lambda: 16 * 1024 * 1024
    )
    async with serving_upstream(recording) as url:
        server = McpServer(name="echo", url=url, protocol_mode="session")
        async with factory(server, {}) as client:
            result = await client.call_tool("echo", {"text": "hi"})
    assert result.content[0].text == "echo:hi"
    assert recording.initializes() == 1
    assert recording.calls("server/discover") == []
