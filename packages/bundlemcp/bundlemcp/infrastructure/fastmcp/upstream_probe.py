"""Probing an upstream server through the MCP client library."""

from typing import Any, Literal

import structlog

from bundlemcp.application.contracts.upstream.upstream_client_factory import UpstreamClientFactory
from bundlemcp.application.contracts.upstream.upstream_probe import ProbeResult
from bundlemcp.domain.servers.listing_kind import ListingKind
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.member_entry_kind import MemberEntryKind
from bundlemcp.domain.servers.probed_entry import ProbedEntry
from bundlemcp.domain.servers.probed_listing import ProbedListing
from bundlemcp.domain.servers.probed_server_info import ProbedServerInfo
from bundlemcp.domain.servers.probed_tool import ProbedTool
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.infrastructure.fastmcp.connection_failure import connection_failure

# the most entries of one kind cached per server; a longer listing is cut, and that is logged
MEMBER_LISTING_LIMIT = 500
# a server that keeps handing out new cursors is not read forever
LISTING_PAGE_LIMIT = 50

# the client method that reads one page of each listing, and the page's field holding its entries
_PAGES: dict[ListingKind, tuple[str, str]] = {
    ListingKind.PROMPTS: ("list_prompts_mcp", "prompts"),
    ListingKind.RESOURCES: ("list_resources_mcp", "resources"),
    ListingKind.RESOURCE_TEMPLATES: ("list_resource_templates_mcp", "resource_templates"),
}
# the listings curation keeps entries of
_CURATED: dict[ListingKind, MemberEntryKind] = {
    ListingKind.PROMPTS: MemberEntryKind.PROMPT,
    ListingKind.RESOURCES: MemberEntryKind.RESOURCE,
}

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
                listings = []
                for kind in ListingKind:
                    if capabilities is None or getattr(capabilities, kind.capability.value) is None:
                        continue
                    listing = await self._listing(server, client, kind)
                    if listing is not None:
                        listings.append(listing)
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
            prompts=self._entries(listings, ListingKind.PROMPTS),
            resources=self._entries(listings, ListingKind.RESOURCES),
            listings=[listing for listing, _ in listings],
            truncated=[
                _CURATED[listing.kind]
                for listing, _ in listings
                if not listing.complete and listing.kind in _CURATED
            ],
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
        server: McpServer, client: Any, kind: ListingKind
    ) -> tuple[ProbedListing, list[dict[str, Any]]] | None:
        """One of the server's listings read to its last page, with the entries kept for
        curation; None when listing it failed.

        Pages are read without the client's response cache, so the scope each
        page carries is the server's own.
        """
        fetch, field = _PAGES[kind]
        entries: list[dict[str, Any]] = []
        scopes: set[str | None] = set()
        cursors: set[str] = set()
        cursor: str | None = None
        ended = False
        try:
            for _ in range(LISTING_PAGE_LIMIT):
                page = await getattr(client, fetch)(cursor=cursor, cache_mode="bypass")
                # the client model fills in 'private' when a server sent no scope
                scopes.add(page.cache_scope if "cache_scope" in page.model_fields_set else None)
                entries.extend(
                    item.model_dump(by_alias=True, mode="json", exclude_none=True)
                    for item in getattr(page, field)
                )
                if len(entries) > MEMBER_LISTING_LIMIT:
                    break
                cursor = page.next_cursor
                # a repeated cursor would only read the same pages again
                if cursor is None or cursor in cursors:
                    ended = True
                    break
                cursors.add(cursor)
        except Exception:
            log.warning("discovery.listing_failed", server=server.name, kind=kind.value)
            return None
        complete = ended and len(entries) <= MEMBER_LISTING_LIMIT
        if not complete:
            log.warning(
                "discovery.listing_truncated",
                server=server.name,
                kind=kind.value,
                listed=len(entries),
                kept=MEMBER_LISTING_LIMIT,
            )
        scope: Literal["public", "private"] | None = None
        if "private" in scopes:
            scope = "private"
        elif scopes == {"public"}:
            scope = "public"
        listing = ProbedListing(
            kind=kind, entries=entries if complete else [], cache_scope=scope, complete=complete
        )
        return listing, entries[:MEMBER_LISTING_LIMIT]

    @staticmethod
    def _entries(
        listings: list[tuple[ProbedListing, list[dict[str, Any]]]], kind: ListingKind
    ) -> list[ProbedEntry] | None:
        """The curation entries of one listing; None when it was not listed."""
        for listing, kept in listings:
            if listing.kind is kind:
                key = kind.key
                return [
                    ProbedEntry(
                        key=entry[key],
                        name=entry.get("name", entry[key]),
                        title=entry.get("title"),
                        description=entry.get("description"),
                    )
                    for entry in kept
                ]
        return None
