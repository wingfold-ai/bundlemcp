"""Probing an upstream server through the MCP client library."""

from bundlemcp.application.contracts.upstream.upstream_client_factory import UpstreamClientFactory
from bundlemcp.application.contracts.upstream.upstream_probe import ProbeResult
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.probed_tool import ProbedTool


class FastMcpUpstreamProbe:
    """One session per probe: list the tools, read what the handshake negotiated."""

    def __init__(self, client_factory: UpstreamClientFactory) -> None:
        self._client_factory = client_factory

    async def probe(self, server: McpServer) -> ProbeResult:
        client = self._client_factory(server, {})
        async with client:
            listed = await client.list_tools()
            capabilities = client.server_capabilities
            protocol_version = client.protocol_version
        return ProbeResult(
            tools=[
                ProbedTool(
                    name=tool.name,
                    title=tool.title,
                    description=tool.description,
                    input_schema=tool.input_schema or {},
                    annotations=(
                        tool.annotations.model_dump(exclude_none=True) if tool.annotations else None
                    ),
                )
                for tool in listed
            ],
            capabilities=(
                capabilities.model_dump(mode="json", by_alias=True, exclude_none=True)
                if capabilities is not None
                else None
            ),
            protocol_version=protocol_version,
        )
