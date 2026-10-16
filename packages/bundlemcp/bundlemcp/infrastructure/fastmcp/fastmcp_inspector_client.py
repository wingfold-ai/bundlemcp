"""An inspector connection over the MCP client library."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import Client
from mcp.shared.exceptions import MCPError

from bundlemcp.application.contracts.inspection.inspector_client import (
    InspectedCall,
    InspectedServer,
    ProgressCallback,
)
from bundlemcp.application.contracts.inspection.inspector_request_failed import (
    InspectorRequestFailed,
)
from bundlemcp.domain.servers.probe_failure import ProbeFailure
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.infrastructure.fastmcp.connection_failure import connection_failure


class FastMcpInspectorClient:
    """One connected client, reporting what the target said in wire JSON.

    A JSON-RPC error answer to ``ping`` or ``tools/list`` raises
    ``InspectorRequestFailed``; one to ``tools/call`` is returned as the
    call's outcome, since showing it is the point of the call.
    """

    def __init__(self, client: Client) -> None:
        self._client = client

    @property
    def server(self) -> InspectedServer:
        info = self._client.server_info
        capabilities = self._client.server_capabilities
        return InspectedServer(
            name=info.name if info is not None else None,
            title=info.title if info is not None else None,
            version=info.version if info is not None else None,
            description=info.description if info is not None else None,
            website_url=info.website_url if info is not None else None,
            protocol_version=self._client.protocol_version,
            capabilities=(
                capabilities.model_dump(mode="json", by_alias=True, exclude_none=True)
                if capabilities is not None
                else {}
            ),
            instructions=self._client.instructions,
        )

    async def ping(self) -> None:
        try:
            await self._client.ping()
        except MCPError as exc:
            raise InspectorRequestFailed(exc.error.code, exc.error.message) from exc

    async def list_tools(self) -> list[dict[str, Any]]:
        try:
            listed = await self._client.list_tools()
        except MCPError as exc:
            raise InspectorRequestFailed(exc.error.code, exc.error.message) from exc
        return [tool.model_dump(mode="json", by_alias=True, exclude_none=True) for tool in listed]

    async def call_tool(
        self, name: str, arguments: dict[str, Any], on_progress: ProgressCallback
    ) -> InspectedCall:
        try:
            result = await self._client.call_tool_mcp(name, arguments, progress_handler=on_progress)
        except MCPError as exc:
            return InspectedCall(error_code=exc.error.code, error_message=exc.error.message)
        return InspectedCall(
            result=result.model_dump(mode="json", by_alias=True, exclude_none=True)
        )


@asynccontextmanager
async def inspector_session(
    build: Callable[[ResponseLog], Client],
) -> AsyncIterator[FastMcpInspectorClient]:
    """A connected inspector client; a connection that fails is a classified ``ProbeFailure``."""
    responses = ResponseLog()
    try:
        async with build(responses) as client:
            yield FastMcpInspectorClient(client)
    except (ProbeFailure, InspectorRequestFailed):
        raise
    except Exception as exc:
        raise connection_failure(exc, responses) from exc
