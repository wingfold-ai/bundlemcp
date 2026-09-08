"""Reaching a bundle's member servers for the read-only passthrough methods."""

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from fastmcp import Client

from bundlemcp.api.mcp.dialect import Era
from bundlemcp.api.mcp.forwarded_headers import forwarded_headers
from bundlemcp.api.mcp.request_context import RequestContext
from bundlemcp.api.mcp.tool_call.client_relay import ClientRelay
from bundlemcp.application.contracts.live_state.signal_bus import SignalBus
from bundlemcp.application.contracts.live_state.stream_registry import StreamRegistry
from bundlemcp.application.contracts.upstream.upstream_client_factory import UpstreamClientFactory
from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.application.upstream_oauth.upstream_credential_resolver import (
    UpstreamCredentialResolver,
)
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect
from bundlemcp.domain.upstream_oauth.upstream_oauth_not_configured import UpstreamOAuthNotConfigured

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
        self,
        client_factory: UpstreamClientFactory,
        credentials: UpstreamCredentialResolver,
        registry: StreamRegistry,
        signals: SignalBus,
        runtime_config: RuntimeConfig,
    ) -> None:
        self._client_factory = client_factory
        self._credentials = credentials
        self._registry = registry
        self._signals = signals
        self._runtime_config = runtime_config

    @property
    def credentials(self) -> UpstreamCredentialResolver:
        return self._credentials

    async def client_for(self, ctx: RequestContext, server: McpServer) -> Client:
        """A client for one member, with forwarded headers and its upstream bearer attached."""
        headers = forwarded_headers(ctx.request.headers, server, ctx.identity.sub)
        headers.update(await self._credentials.headers_for(server, ctx.identity))
        handlers: dict[str, Any] = {}
        if ctx.era is Era.HANDSHAKE:
            # PROT-4: a handshake client's GET stream answers an upstream's requests
            # for input on any method. A modern client's requests on prompts/get
            # and resources/read are not bridged yet (PROT-18 residual).
            timeouts = await self._runtime_config.call_timeouts()
            relay = ClientRelay(
                self._registry,
                self._signals,
                ctx.routing_key,
                timeouts.max_total,
                log_level=ctx.log_level,
                on_notification=None,
                channel=None,
            )
            handlers = relay.client_kwargs(ctx.client_capabilities)
        return self._client_factory(server, headers, **handlers)

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
