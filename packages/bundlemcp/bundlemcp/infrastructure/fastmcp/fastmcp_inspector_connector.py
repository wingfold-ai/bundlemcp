from contextlib import AbstractAsyncContextManager

from bundlemcp.application.contracts.inspection.inspector_client import InspectorClient
from bundlemcp.application.contracts.upstream.upstream_client_factory import UpstreamClientFactory
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.infrastructure.fastmcp.fastmcp_inspector_client import inspector_session


class FastMcpInspectorConnector:
    """Inspector connections to upstreams, built by the gateway's own client factory.

    The factory is the one tool calls use, so the egress policy, the response
    cap and the stored static headers apply to the inspector unchanged.
    """

    def __init__(self, client_factory: UpstreamClientFactory) -> None:
        self._client_factory = client_factory

    def open(
        self, server: McpServer, headers: dict[str, str]
    ) -> AbstractAsyncContextManager[InspectorClient]:
        return inspector_session(
            lambda responses: self._client_factory(server, headers, observer=responses)
        )
