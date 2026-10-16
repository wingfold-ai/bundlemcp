"""Probing an upstream server through the MCP client library."""

from typing import Any

import structlog

from bundlemcp.application.contracts.upstream.upstream_client_factory import UpstreamClientFactory
from bundlemcp.application.contracts.upstream.upstream_probe import ProbeResult
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.member_entry_kind import MemberEntryKind
from bundlemcp.domain.servers.probed_entry import ProbedEntry
from bundlemcp.domain.servers.probed_server_info import ProbedServerInfo
from bundlemcp.domain.servers.probed_tool import ProbedTool
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.infrastructure.fastmcp.connection_failure import connection_failure

# the most entries of one kind cached per server; a longer listing is cut, and that is logged
MEMBER_LISTING_LIMIT = 500

log = structlog.get_logger(__name__)


class FastMcpUpstreamProbe:
    """One session per probe: list the tools, read what the connection negotiated.

    A probe that gets no MCP answer raises ``ProbeFailure`` classified from
    the HTTP responses the transport observed, because the MCP client reports
    a refused credential, a missing endpoint and a web page all as one error.
    """

    def __init__(self, client_factory: UpstreamClientFactory) -> None:
        self._client_factory = client_factory

    async def probe(self, server: McpServer, headers: dict[str, str]) -> ProbeResult:
        responses = ResponseLog()
        try:
            client = self._client_factory(server, headers, observer=responses)
            async with client:
                listed = await client.list_tools()
                capabilities = client.server_capabilities
                protocol_version = client.protocol_version
                info = client.server_info
                truncated: list[MemberEntryKind] = []
                prompts = (
                    await self._listing(
                        server, client.list_prompts, MemberEntryKind.PROMPT, truncated
                    )
                    if capabilities is not None and capabilities.prompts is not None
                    else None
                )
                resources = (
                    await self._listing(
                        server, client.list_resources, MemberEntryKind.RESOURCE, truncated
                    )
                    if capabilities is not None and capabilities.resources is not None
                    else None
                )
        except Exception as exc:
            raise connection_failure(exc, responses) from exc
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
            prompts=prompts,
            resources=resources,
            truncated=truncated,
            server_info=(
                ProbedServerInfo(
                    name=info.name,
                    title=info.title,
                    description=info.description,
                    version=info.version,
                    website_url=info.website_url,
                )
                if info is not None
                else None
            ),
        )

    @staticmethod
    async def _listing(
        server: McpServer, fetch: Any, kind: MemberEntryKind, truncated: list[MemberEntryKind]
    ) -> list[ProbedEntry] | None:
        """One of the server's listings as cache entries; None when listing it failed."""
        try:
            listed = await fetch()
        except Exception:
            log.warning("discovery.listing_failed", server=server.name, kind=kind.value)
            return None
        if len(listed) > MEMBER_LISTING_LIMIT:
            log.warning(
                "discovery.listing_truncated",
                server=server.name,
                kind=kind.value,
                listed=len(listed),
                kept=MEMBER_LISTING_LIMIT,
            )
            truncated.append(kind)
            listed = listed[:MEMBER_LISTING_LIMIT]
        if kind is MemberEntryKind.PROMPT:
            return [
                ProbedEntry(key=p.name, name=p.name, title=p.title, description=p.description)
                for p in listed
            ]
        return [
            ProbedEntry(key=str(r.uri), name=r.name, title=r.title, description=r.description)
            for r in listed
        ]
