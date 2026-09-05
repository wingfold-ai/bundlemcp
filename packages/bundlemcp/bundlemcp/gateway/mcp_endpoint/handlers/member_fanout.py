"""Reaching a bundle's member servers for the read-only passthrough methods."""

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from fastmcp import Client

from bundlemcp.gateway.mcp_endpoint.forwarded_headers import forwarded_headers
from bundlemcp.gateway.mcp_endpoint.request_context import RequestContext
from bundlemcp.gateway.mcp_endpoint.upstream_credentials import UpstreamCredentialResolver
from bundlemcp.gateway.upstream import ClientFactory
from bundlemcp.models import McpServer
from bundlemcp.oauth.upstream_client import NeedsConnect, UpstreamOAuthNotConfigured

log = structlog.get_logger(__name__)

MemberCall = Callable[[Client], Awaitable[Any]]


def dump(obj: Any) -> dict[str, Any]:
    return obj.model_dump(by_alias=True, mode="json", exclude_none=True)


class MemberFanout:
    """Runs a read-only MCP call against one member or all of them.

    Live and uncurated, unlike the tool surface. A member that is unreachable
    or not connected is skipped with a warning, so the rest still answer.
    """

    def __init__(
        self, client_factory: ClientFactory, credentials: UpstreamCredentialResolver
    ) -> None:
        self._client_factory = client_factory
        self._credentials = credentials

    @property
    def credentials(self) -> UpstreamCredentialResolver:
        return self._credentials

    async def client_for(self, ctx: RequestContext, server: McpServer) -> Client:
        """A client for one member, with forwarded headers and its upstream bearer attached."""
        headers = forwarded_headers(ctx.request.headers, server, ctx.identity.sub)
        headers.update(await self._credentials.headers_for(server, ctx.identity))
        return self._client_factory(server, headers)

    async def call(self, ctx: RequestContext, server: McpServer, call: MemberCall) -> Any:
        """Run one call against one member; connection errors propagate to the caller."""
        client = await self.client_for(ctx, server)
        async with client:
            return await call(client)

    async def each(
        self, ctx: RequestContext, call: MemberCall
    ) -> list[tuple[McpServer, Any | None]]:
        """Every member's answer, with None where a member could not be asked."""
        results: list[tuple[McpServer, Any | None]] = []
        for server in ctx.view.servers.values():
            try:
                results.append((server, await self.call(ctx, server, call)))
            except (NeedsConnect, UpstreamOAuthNotConfigured):
                log.warning("passthrough.member_unconnected", server=server.name)
                results.append((server, None))
            except Exception:
                log.warning("passthrough.member_failed", server=server.name, exc_info=True)
                results.append((server, None))
        return results

    async def first(self, ctx: RequestContext, call: MemberCall) -> Any | None:
        """The first member that answers, or None when none does."""
        for server in ctx.view.servers.values():
            try:
                return await self.call(ctx, server, call)
            except Exception:
                log.warning("passthrough.member_failed", server=server.name)
                continue
        return None

    async def merged(
        self,
        ctx: RequestContext,
        call: MemberCall,
        *,
        key: str,
        present: Callable[[McpServer, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Every member's list, concatenated and de-duplicated by ``key``."""
        items: list[dict[str, Any]] = []
        seen: set[Any] = set()
        for server, member_items in await self.each(ctx, call):
            if member_items is None:
                continue
            for obj in member_items:
                entry = dump(obj)
                if present is not None:
                    entry = present(server, entry)
                identity = entry.get(key)
                if identity in seen:
                    log.warning("passthrough.collision", key=identity, server=server.name)
                    continue
                seen.add(identity)
                items.append(entry)
        return items
