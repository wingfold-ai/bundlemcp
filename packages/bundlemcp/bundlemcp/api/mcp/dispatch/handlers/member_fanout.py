"""Reaching a bundle's member servers for the read-only passthrough methods."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastmcp import Client

from bundlemcp.api.mcp.protocol.dialect import ProtocolEra
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.api.mcp.relay.client_relay import ClientRelay
from bundlemcp.api.mcp.relay.input_channel import InputChannel
from bundlemcp.api.mcp.upstream.jsonrpc_code import jsonrpc_code
from bundlemcp.api.mcp.upstream.upstream_leases import UpstreamLeases
from bundlemcp.application.contracts.live_state.signal_bus import SignalBus
from bundlemcp.application.contracts.live_state.stream_presence import StreamPresence
from bundlemcp.application.contracts.live_state.stream_registry import StreamRegistry
from bundlemcp.application.contracts.upstream.upstream_session_pool import UpstreamLease
from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.application.upstream_oauth.upstream_credential_resolver import (
    UpstreamCredentialResolver,
)
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.domain.servers.server_capability import ServerCapability
from bundlemcp.domain.sessions.upstream_failure import UpstreamFailure
from bundlemcp.domain.sessions.upstream_retry_policy import UpstreamRetryPolicy
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect
from bundlemcp.domain.upstream_oauth.upstream_oauth_not_configured import UpstreamOAuthNotConfigured

log = structlog.get_logger(__name__)

MemberCall = Callable[[Client], Awaitable[Any]]

# the passthrough methods only read, so a lost connection is worth one more try
READ_RETRY = UpstreamRetryPolicy(read_only=True)


def dump(obj: Any) -> dict[str, Any]:
    return obj.model_dump(by_alias=True, mode="json", exclude_none=True)


class MemberFanout:
    """Runs a read-only MCP call against one member or all of them.

    Live and uncurated, unlike the tool surface. Only members that advertised
    the method's capability at their last discovery are asked, so a member
    without it is never woken. A member that is unreachable or not connected
    is skipped with a warning, so the rest still answer.
    """

    def __init__(
        self,
        leases: UpstreamLeases,
        registry: StreamRegistry,
        signals: SignalBus,
        presence: StreamPresence,
        runtime_config: RuntimeConfig,
    ) -> None:
        self._leases = leases
        self._registry = registry
        self._signals = signals
        self._presence = presence
        self._runtime_config = runtime_config

    @property
    def credentials(self) -> UpstreamCredentialResolver:
        return self._leases.credentials

    @property
    def leases(self) -> UpstreamLeases:
        return self._leases

    @asynccontextmanager
    async def lease(
        self,
        ctx: RequestContext,
        server: McpServer,
        *,
        channel: InputChannel | None = None,
        bound: bool = False,
        responses: ResponseLog | None = None,
        fresh: bool = False,
        dedicated_to: str | None = None,
    ) -> AsyncIterator[UpstreamLease]:
        """An upstream session for one member, with forwarded headers and its bearer attached.

        ``channel`` is how a modern client is asked for the input a handshake
        member requests; without one such a member sees the client as unable to
        answer. ``bound`` runs the request on the upstream session dedicated to
        a handshake client's session, for state the member keeps per session;
        ``dedicated_to`` dedicates one to another client stream instead.
        """
        forwarded, credentials = await self._leases.headers(ctx, server)
        handlers: dict[str, Any] = {}
        if ctx.era is ProtocolEra.SESSION or channel is not None:
            # a handshake client's GET stream answers an upstream's requests
            # for input on any method; a modern client's, the channel
            timeouts = await self._runtime_config.call_timeouts()
            relay = ClientRelay(
                self._registry,
                self._signals,
                self._presence,
                ctx.routing_key,
                timeouts.max_total,
                log_level=ctx.log_level,
                on_notification=None,
                channel=channel,
            )
            handlers = relay.client_kwargs(ctx.client_capabilities)
        request = self._leases.request(
            ctx,
            server,
            forwarded=forwarded,
            credentials=credentials,
            handlers=handlers,
            bound=bound and ctx.session is not None,
            responses=responses,
            fresh=fresh,
            dedicated_to=dedicated_to,
        )
        async with self._leases.lease(request, ctx.session if bound else None) as lease:
            yield lease

    async def call(
        self, ctx: RequestContext, server: McpServer, call: MemberCall, *, bound: bool = False
    ) -> Any:
        """Run one call against one member; connection errors propagate to the caller.

        A read is sent once more when its session expired or its connection was
        lost, since reading twice changes nothing.
        """
        fresh = False
        while True:
            responses = ResponseLog()
            try:
                async with self.lease(
                    ctx, server, bound=bound, responses=responses, fresh=fresh
                ) as lease:
                    return await call(lease.client)
            except Exception as exc:
                failure = UpstreamFailure.of(responses, jsonrpc_code=jsonrpc_code(exc))
                if not READ_RETRY.allows_retry(failure, retried=fresh):
                    raise
                log.info("passthrough.member_retried", server=server.name, failure=failure)
                fresh = True

    @staticmethod
    def members(ctx: RequestContext, capability: ServerCapability) -> list[McpServer]:
        """The bundle's members that advertise ``capability``, in bundle order."""
        # a member without the capability is not contacted (ADR-0043)
        return [server for server in ctx.view.servers.values() if server.advertises(capability)]

    async def each(
        self, ctx: RequestContext, call: MemberCall, *, capability: ServerCapability
    ) -> list[tuple[McpServer, Any | None]]:
        """Every capable member's answer, with None where a member could not be asked."""
        results: list[tuple[McpServer, Any | None]] = []
        for server in self.members(ctx, capability):
            try:
                results.append((server, await self.call(ctx, server, call)))
            except (NeedsConnect, UpstreamOAuthNotConfigured):
                log.warning("passthrough.member_unconnected", server=server.name)
                results.append((server, None))
            except Exception:
                log.warning("passthrough.member_failed", server=server.name, exc_info=True)
                results.append((server, None))
        return results

    async def first(
        self,
        ctx: RequestContext,
        call: MemberCall,
        *,
        capability: ServerCapability,
        among: list[McpServer] | None = None,
    ) -> Any | None:
        """The first capable member that answers, or None when none does.

        ``among`` narrows the members asked, in member order.
        """
        for server in among if among is not None else self.members(ctx, capability):
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
        capability: ServerCapability,
        key: str,
        present: Callable[[McpServer, dict[str, Any]], dict[str, Any] | None] | None = None,
    ) -> list[dict[str, Any]]:
        """Every capable member's list, concatenated and de-duplicated by ``key``.

        ``present`` shapes each entry for the client, or returns None to leave it
        out. A left-out entry still claims its key, so a later member's entry
        under the same key does not take its place.
        """
        items: list[dict[str, Any]] = []
        seen: set[Any] = set()
        for server, member_items in await self.each(ctx, call, capability=capability):
            if member_items is None:
                continue
            for obj in member_items:
                entry = dump(obj)
                presented = present(server, entry) if present is not None else entry
                identity = (presented if presented is not None else entry).get(key)
                if identity in seen:
                    log.warning("passthrough.collision", key=identity, server=server.name)
                    continue
                seen.add(identity)
                if presented is not None:
                    items.append(presented)
        return items
