"""Turning a request the gateway serves into a lease on an upstream session."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog

from bundlemcp.api.mcp.protocol.header_forwarding import HeaderForwarding
from bundlemcp.api.mcp.protocol.request_context import RequestContext
from bundlemcp.api.mcp.protocol.session_request_context import SessionRequestContext
from bundlemcp.application.contracts.live_state.resource_subscriptions import (
    ResourceSubscriptions,
)
from bundlemcp.application.contracts.live_state.session_store import SessionStore
from bundlemcp.application.contracts.upstream.upstream_session_pool import (
    UpstreamLease,
    UpstreamLeaseRequest,
    UpstreamSessionPool,
)
from bundlemcp.application.upstream_oauth.upstream_credential_resolver import (
    UpstreamCredentialResolver,
)
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.domain.sessions.session_record import SessionRecord
from bundlemcp.domain.sessions.upstream_session_key import UpstreamSessionKey
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect
from bundlemcp.domain.upstream_oauth.upstream_oauth_not_configured import UpstreamOAuthNotConfigured

log = structlog.get_logger(__name__)


class UpstreamLeases:
    """Builds lease requests for the edge's requests, and records the bindings they make.

    A handshake session's own operations on a member — a tool call, setLevel,
    a resource subscription — are bound: they run on the upstream session
    dedicated to that session, whose binding is written back to the session
    record whenever it changes. Everything else is unbound and may share a
    pooled session with other requests under the same key.
    """

    def __init__(
        self,
        pool: UpstreamSessionPool,
        sessions: SessionStore,
        header_forwarding: HeaderForwarding,
        credentials: UpstreamCredentialResolver,
        subscriptions: ResourceSubscriptions,
    ) -> None:
        self._pool = pool
        self._sessions = sessions
        self._subscriptions = subscriptions
        self._header_forwarding = header_forwarding
        self._credentials = credentials

    @property
    def pool(self) -> UpstreamSessionPool:
        return self._pool

    @property
    def credentials(self) -> UpstreamCredentialResolver:
        return self._credentials

    @property
    def subscriptions(self) -> ResourceSubscriptions:
        return self._subscriptions

    async def headers(
        self, ctx: RequestContext, server: McpServer, *, force_refresh: bool = False
    ) -> tuple[dict[str, str], dict[str, str]]:
        """The headers a request of ``ctx`` sends ``server``: forwarded ones, then credentials.

        The forwarded headers are the caller's own and the identity header,
        the same on every request of that caller. The credentials — an
        upstream bearer or a delegated token — are minted or refreshed for this
        request and win over a forwarded header of the same name.
        """
        credentials = await self._credentials.headers_for(
            server, ctx.identity, endpoint=ctx.view.endpoint.name, force_refresh=force_refresh
        )
        replaced = {name.lower() for name in credentials}
        forwarded = {
            name: value
            for name, value in self._header_forwarding.headers_for(
                ctx.request.headers, server, ctx.identity
            ).items()
            if name.lower() not in replaced
        }
        return forwarded, credentials

    def request(
        self,
        ctx: RequestContext,
        server: McpServer,
        *,
        forwarded: dict[str, str],
        credentials: dict[str, str],
        handlers: dict[str, Any],
        bound: bool,
        responses: ResponseLog | None = None,
        fresh: bool = False,
        dedicated_to: str | None = None,
    ) -> UpstreamLeaseRequest:
        """A lease request for ``ctx`` on ``server``.

        ``bound`` runs it on the upstream session of the handshake session
        ``ctx`` names, if it names one; ``dedicated_to`` instead dedicates a
        new upstream session to another client stream, such as a modern
        client's listen stream.
        """
        session = ctx.session if bound else None
        return UpstreamLeaseRequest(
            server=server,
            key=UpstreamSessionKey.for_request(
                server,
                sub=ctx.identity.sub,
                forwarded_headers=forwarded,
                endpoint=ctx.view.endpoint.name,
            ),
            headers=forwarded,
            credentials=credentials,
            handlers=handlers,
            responses=responses if responses is not None else ResponseLog(),
            bound_to=session.session_id if session is not None else dedicated_to,
            binding=session.bindings.get(server.name) if session is not None else None,
            fresh=fresh,
        )

    @asynccontextmanager
    async def lease(
        self, request: UpstreamLeaseRequest, session: SessionRecord | None
    ) -> AsyncIterator[UpstreamLease]:
        """A lease for ``request``; a binding it makes or changes is recorded on ``session``."""
        async with self._pool.lease(request) as lease:
            if (
                session is not None
                and lease.binding is not None
                and lease.binding != request.binding
            ):
                updated = await self._sessions.set_binding(session.session_id, lease.binding)
                if updated is not None:
                    session.bindings[request.server.name] = lease.binding
                if request.binding is not None:
                    await self._resubscribe(lease, session.session_id, request.server)
            yield lease

    async def _resubscribe(self, lease: UpstreamLease, stream_id: str, server: McpServer) -> None:
        """Renew a stream's subscriptions to ``server`` on the new session that replaced its old."""
        for subscription in await self._subscriptions.of_stream(stream_id):
            if subscription.server_name != server.name:
                continue
            try:
                await lease.subscribe(subscription.uri)
            except Exception:
                log.warning("resources.resubscribe_failed", server=server.name, exc_info=True)

    async def end_session(self, ctx: SessionRequestContext) -> None:
        """End the upstream sessions bound to the handshake session ``ctx`` names.

        Each is ended with the caller's own headers, as its requests were; an
        upstream that cannot be told is left to expire its session.
        """
        await self._subscriptions.drop_stream(ctx.session.session_id)
        for binding in ctx.session.bindings.values():
            server = ctx.view.servers.get(binding.server_name)
            if server is None or binding.upstream_session_id is None:
                continue
            try:
                forwarded, credentials = await self.headers(ctx, server)
            except (NeedsConnect, UpstreamOAuthNotConfigured):
                forwarded, credentials = (
                    self._header_forwarding.headers_for(ctx.request.headers, server, ctx.identity),
                    {},
                )
            try:
                await self._pool.end(server, binding, {**forwarded, **credentials})
            except Exception:
                log.info("upstream_session.end_failed", server=server.name, exc_info=True)
