"""Inspector connections to this gateway's own endpoints, without leaving the process."""

from contextlib import AbstractAsyncContextManager

import httpx2
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from mcp.shared._httpx_utils import MCP_DEFAULT_SSE_READ_TIMEOUT, MCP_DEFAULT_TIMEOUT
from starlette.types import ASGIApp

from bundlemcp.application.contracts.inspection.inspector_client import InspectorClient
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.infrastructure.fastmcp.fastmcp_inspector_client import inspector_session
from bundlemcp.infrastructure.fastmcp.in_process_asgi_transport import InProcessAsgiTransport
from bundlemcp.infrastructure.fastmcp.response_observer import ResponseObserver


class InProcessEndpointClients:
    """MCP clients whose requests the gateway's own app serves in this process.

    A request enters ``/{endpoint}/mcp`` exactly as a remote client's does,
    and the egress policy is not involved: nothing is dialled, so neither the
    gateway's loopback address nor its public hostname has to be reachable.
    """

    def __init__(self, app: ASGIApp, *, public_base: str) -> None:
        self._app = app
        self._public_base = public_base.rstrip("/")

    def open(
        self, endpoint: str, headers: dict[str, str], *, client_ip: str
    ) -> AbstractAsyncContextManager[InspectorClient]:
        def http_client(
            headers: dict[str, str] | None = None,
            timeout: httpx2.Timeout | None = None,
            auth: httpx2.Auth | None = None,
            follow_redirects: bool = False,
        ) -> httpx2.AsyncClient:
            return httpx2.AsyncClient(
                headers=headers,
                timeout=timeout
                or httpx2.Timeout(MCP_DEFAULT_TIMEOUT, read=MCP_DEFAULT_SSE_READ_TIMEOUT),
                auth=auth,
                transport=InProcessAsgiTransport(self._app, client=(client_ip, 0)),
                trust_env=False,
            )

        def build(responses: ResponseLog) -> Client:
            return Client(
                StreamableHttpTransport(
                    f"{self._public_base}/{endpoint}/mcp",
                    headers=headers,
                    auth=ResponseObserver(responses),
                    httpx_client_factory=http_client,
                )
            )

        return inspector_session(build)
