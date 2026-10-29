"""Upstream MCP sessions held open on this replica and handed out one request at a time."""

import asyncio
import time
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastmcp import Client
from mcp.client.subscriptions import listen
from mcp_types import SubscriptionFilter
from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.application.contracts.upstream.member_notification import (
    ListedKind,
    MemberListChanged,
    MemberNotification,
    MemberResourceUpdated,
)
from bundlemcp.application.contracts.upstream.upstream_client_factory import UpstreamClientFactory
from bundlemcp.application.contracts.upstream.upstream_notification_sink import (
    UpstreamNotificationSink,
)
from bundlemcp.application.contracts.upstream.upstream_session_pool import UpstreamLeaseRequest
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.sessions.upstream_binding import UpstreamBinding
from bundlemcp.infrastructure.fastmcp.lease_slot import LeaseSlot
from bundlemcp.infrastructure.fastmcp.lease_transport import lease_transport_for
from bundlemcp.infrastructure.fastmcp.member_notification_translation import (
    from_listen_event,
    from_log_message,
    from_server_notification,
)
from bundlemcp.infrastructure.fastmcp.pooled_session import PooledSession, SessionState
from bundlemcp.infrastructure.fastmcp.resource_watch import (
    ListenResourceWatch,
    ResourceWatch,
    SubscribeResourceWatch,
)

log = structlog.get_logger(__name__)

# the client keywords whose presence changes what a session advertises at initialize
RELAY_KEYWORDS = frozenset({"elicitation_handler", "sampling_handler", "roots"})
LOG_HANDLER = "log_handler"
LISTEN_RETRY_SECONDS = 1.0


class PoolLimits(BaseModel):
    """The caps and idle timeout in force at one checkout."""

    model_config = ConfigDict(frozen=True)

    total: int = Field(ge=1, description="Upstream sessions this replica holds open at most")
    per_server: int = Field(ge=1, description="Upstream sessions held open per server at most")
    idle_timeout: float = Field(
        gt=0, description="Seconds an unused session is kept before it is closed"
    )


class PooledLease(BaseModel):
    """One request's use of a pooled session."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    binding: UpstreamBinding | None = Field(
        description="The binding that now names the session; None for an unbound request"
    )
    session: PooledSession = Field(exclude=True, description="The session the lease is on")

    @property
    def client(self) -> Client:
        """The SDK client the request is sent through."""
        client = self.session.client
        if client is None:
            raise RuntimeError("a lease is handed out only once its session's transport is open")
        return client

    async def subscribe(self, uri: str) -> None:
        await self._resource_watch.subscribe(self.session, uri)

    async def unsubscribe(self, uri: str) -> None:
        await self._resource_watch.unsubscribe(self.session, uri)

    @property
    def _resource_watch(self) -> ResourceWatch:
        watch = self.session.resource_watch
        if watch is None:
            raise RuntimeError("a lease is handed out only once its session's transport is open")
        return watch


class PooledUpstreamSessions:
    """Keeps upstream sessions open across requests, one request per session at a time.

    A session is reused only for a request with an equal key, the same relay
    callbacks and, for a handshake session, the same downstream session. A
    handshake session's binding is continued on a new transport when no
    transport to it is held here, so a session opened on another replica
    goes on without a second ``initialize``. At a cap the least recently used
    idle session is closed, shared ones first; when none is idle the request
    is served on a connection of its own.

    A shared session that is evicted or idles out is ended upstream; a bound
    one only loses its transport, since its binding may still be continued.
    """

    def __init__(
        self,
        factory: UpstreamClientFactory,
        limits: Callable[[], PoolLimits],
        notifications: UpstreamNotificationSink,
    ) -> None:
        self._transport = lease_transport_for(factory)
        self._subscribe_watch = SubscribeResourceWatch()
        self._listen_watch = ListenResourceWatch(self.relisten)
        self._limits = limits
        self._notifications = notifications
        self._sessions: list[PooledSession] = []
        self._lock = asyncio.Lock()
        self._closing: set[asyncio.Task[None]] = set()
        self._reaper: asyncio.Task[None] | None = None

    @property
    def held(self) -> list[PooledSession]:
        """The sessions held now, leased or idle; for inspection only."""
        return list(self._sessions)

    def start(self) -> None:
        self._reaper = asyncio.create_task(self._reap())

    @asynccontextmanager
    async def lease(self, request: UpstreamLeaseRequest) -> AsyncIterator[PooledLease]:
        session = await self._checkout(request)
        caller_headers = {**request.headers, **request.credentials}
        session.slot.begin(caller_headers, request.handlers, request.responses)
        try:
            if not session.is_open:
                await self._connect(session)
            yield PooledLease(
                binding=session.binding() if session.bound_to is not None else None,
                session=session,
            )
        except BaseException:
            # the transport may be broken mid-message; never hand it out again
            self._discard(session, end=False)
            raise
        await self._release(session)

    async def end(
        self, server: McpServer, binding: UpstreamBinding, headers: dict[str, str]
    ) -> None:
        """End a bound upstream session, closing any transport to it held here."""
        if binding.upstream_session_id is None:
            return
        async with self._lock:
            held = [
                session
                for session in self._sessions
                if session.upstream_session_id == binding.upstream_session_id
                and session.key.server_name == server.name
            ]
            for session in held:
                # the upstream session is ended below, so closing the transport must not end it
                self._retire(session, end=False)
        try:
            await self._transport.end_session(
                server, binding.upstream_session_id, binding.protocol_version, headers
            )
        except Exception:
            log.info("upstream_session.end_failed", server=server.name, exc_info=True)

    async def invalidate(self, server_name: str) -> None:
        await self._invalidate(lambda session: session.key.server_name == server_name)

    async def invalidate_all(self) -> None:
        await self._invalidate(lambda session: True)

    async def close(self) -> None:
        if self._reaper is not None:
            self._reaper.cancel()
            self._reaper = None
        async with self._lock:
            sessions, self._sessions = self._sessions, []
        for session in sessions:
            await self._close(session, end=session.bound_to is None)
        if self._closing:
            await asyncio.gather(*self._closing, return_exceptions=True)

    async def _invalidate(self, affected: Callable[[PooledSession], bool]) -> None:
        async with self._lock:
            for session in [session for session in self._sessions if affected(session)]:
                self._retire(session, end=True)

    def _retire(self, session: PooledSession, *, end: bool) -> None:
        """Close an idle session now, and a leased one when its lease ends."""
        if session.state is SessionState.IDLE:
            self._evict(session, end=end)
        else:
            session.retire()

    async def _checkout(self, request: UpstreamLeaseRequest) -> PooledSession:
        relay = frozenset(name for name in request.handlers if name in RELAY_KEYWORDS)
        variant = self._transport.variant(request)
        limits = self._limits()
        async with self._lock:
            wanted = self._continued_id(request)
            reused = self._reuse(request, relay, variant, wanted)
            if reused is not None:
                return reused
            return self._open(request, relay, variant, wanted, limits)

    def _reuse(
        self,
        request: UpstreamLeaseRequest,
        relay: frozenset[str],
        variant: str | None,
        wanted: str | None,
    ) -> PooledSession | None:
        """Lease an idle session that may serve the request, if one is held."""
        for session in list(self._sessions):
            if session.state is not SessionState.IDLE or not session.serves(
                request.key, relay, variant, request.bound_to
            ):
                continue
            if request.fresh:
                # the session a retry gave up on had expired; its idle siblings likely too
                self._evict(session, end=False)
            elif wanted is None or session.upstream_session_id == wanted:
                session.checkout()
                return session
        return None

    def _open(
        self,
        request: UpstreamLeaseRequest,
        relay: frozenset[str],
        variant: str | None,
        wanted: str | None,
        limits: PoolLimits,
    ) -> PooledSession:
        """A new leased session for the request, held when it fits under the caps."""
        pooled = self._make_room(request.server.name, limits)
        session = PooledSession(
            server=request.server,
            key=request.key,
            relay=relay,
            variant=variant,
            bound_to=request.bound_to,
            slot=LeaseSlot(),
            pooled=pooled,
        )
        if wanted is not None and variant is None:
            session.upstream_session_id = wanted
            session.protocol_version = request.binding.protocol_version  # type: ignore[union-attr]
            session.slot.continue_session(wanted, session.protocol_version)
        if pooled:
            self._sessions.append(session)
        return session

    @staticmethod
    def _continued_id(request: UpstreamLeaseRequest) -> str | None:
        """The upstream session a bound request must continue, if it must continue one."""
        binding = request.binding
        if request.bound_to is None or request.fresh or binding is None:
            return None
        return binding.upstream_session_id if binding.continues(request.key) else None

    def _make_room(self, server_name: str, limits: PoolLimits) -> bool:
        """Evict idle sessions until one more fits under both caps; False when none can go."""
        return self._trim_to(limits.total - 1, _everywhere) and self._trim_to(
            limits.per_server - 1, _on_server(server_name)
        )

    def _trim_to(self, cap: int, within: Callable[[PooledSession], bool]) -> bool:
        """Evict idle sessions ``within`` until at most ``cap`` remain; False when none can go."""
        while True:
            scope = [session for session in self._sessions if within(session)]
            if len(scope) <= cap:
                return True
            victim = self._eviction_candidate(scope)
            if victim is None:
                return False
            self._evict(victim, end=victim.ends_upstream_on_eviction)

    @staticmethod
    def _eviction_candidate(sessions: list[PooledSession]) -> PooledSession | None:
        idle = [session for session in sessions if session.evictable]
        if not idle:
            return None
        # identity-free sessions go first: any request can open another one
        return min(idle, key=lambda s: (not s.key.is_shared, s.last_used))

    async def _connect(self, session: PooledSession) -> None:
        client = self._transport.open(
            session.server,
            session.slot,
            continues=session.upstream_session_id is not None,
            handlers=self._handlers(session),
        )
        await client.__aenter__()
        session.client = client
        if session.upstream_session_id is None:
            transport_session = getattr(client.transport, "get_session_id", None)
            session.upstream_session_id = transport_session() if transport_session else None
            session.protocol_version = client.protocol_version
        # the negotiated revision decides, once, how resource updates are asked for
        session.resource_watch = self._listen_watch if session.is_modern else self._subscribe_watch
        self.relisten(session)

    def relisten(self, session: PooledSession) -> None:
        """(Re)open a modern session's standing listen for what it should now hear."""
        if session.listener is not None:
            session.listener.cancel()
            session.listener = None
        if session.is_open and session.is_modern and self._listen_filter(session):
            session.listener = asyncio.create_task(self._listen(session))

    @staticmethod
    def _listen_filter(session: PooledSession) -> dict[str, Any]:
        """The list changes the server advertised, and the resources the session subscribed to."""
        capabilities = session.server.capabilities

        def changes(capability: str) -> bool:
            return bool((capabilities.get(capability) or {}).get("listChanged"))

        wanted: dict[str, Any] = {
            "tools_list_changed": changes("tools"),
            "prompts_list_changed": changes("prompts"),
            "resources_list_changed": changes("resources"),
            "resource_subscriptions": sorted(session.subscriptions),
        }
        return {name: value for name, value in wanted.items() if value}

    async def _listen(self, session: PooledSession) -> None:
        """Hold the session's listen stream open, re-opening it whenever it ends.

        The protocol replays nothing on a re-opened stream, so after every
        re-open but the task's first, whatever it listens for is reported as
        changed: clients then fetch again what they may have missed. A task
        is started anew when the filter changes, which loses nothing.
        """
        assert session.client is not None
        acknowledged_before = False
        while session.is_open:
            try:
                async with listen(session.client.session, **self._listen_filter(session)) as events:
                    if acknowledged_before:
                        await self._refetch(session, events.honored)
                    acknowledged_before = True
                    async for event in events:
                        notification = from_listen_event(event)
                        if notification is not None:
                            await self._notify(session, notification)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.debug("upstream_session.listen_lost", server=session.server.name, exc_info=True)
            await asyncio.sleep(LISTEN_RETRY_SECONDS)

    async def _refetch(self, session: PooledSession, honored: SubscriptionFilter) -> None:
        """Report every list and resource a re-opened listen stream watches as changed."""
        listened = {
            ListedKind.TOOLS: honored.tools_list_changed,
            ListedKind.PROMPTS: honored.prompts_list_changed,
            ListedKind.RESOURCES: honored.resources_list_changed,
        }
        for listed, wanted in listened.items():
            if wanted:
                await self._notify(session, MemberListChanged(listed=listed))
        for uri in honored.resource_subscriptions or ():
            await self._notify(session, MemberResourceUpdated(uri=uri))

    def _handlers(self, session: PooledSession) -> dict[str, Any]:
        """Callbacks that forward to the current lease's, so one transport serves many leases."""
        slot = session.slot

        def forward(name: str) -> Callable[..., Any]:
            async def handler(*args: Any, **kwargs: Any) -> Any:
                return await slot.handlers[name](*args, **kwargs)

            return handler

        handlers: dict[str, Any] = {name: forward(name) for name in session.relay}

        async def log_handler(message: Any) -> None:
            current = slot.handlers.get(LOG_HANDLER)
            if current is not None:
                await current(message)
            elif slot.responses is None and session.bound_to is not None:
                # between requests the message belongs to the session the upstream one serves
                notification = from_log_message(message)
                if notification is not None:
                    await self._notify(session, notification)

        async def message_handler(message: Any) -> None:
            notification = from_server_notification(message)
            if notification is not None:
                await self._notify(session, notification)

        handlers[LOG_HANDLER] = log_handler
        handlers["message_handler"] = message_handler
        return handlers

    async def _notify(self, session: PooledSession, notification: MemberNotification) -> None:
        try:
            await self._notifications.received(
                session.server, notification, bound_to=session.bound_to
            )
        except Exception:
            log.warning(
                "upstream_session.notification_failed",
                server=session.server.name,
                kind=notification.kind,
                exc_info=True,
            )

    async def _release(self, session: PooledSession) -> None:
        session.slot.finish()
        async with self._lock:
            session.release()
            session.last_used = time.monotonic()
            if not session.pooled or session.state is SessionState.RETIRING:
                self._evict(session, end=True)

    def _discard(self, session: PooledSession, *, end: bool) -> None:
        session.slot.finish()
        self._evict(session, end=end)

    def _evict(self, session: PooledSession, *, end: bool) -> None:
        """Stop holding the session and close its transport; ``end`` ends it upstream too."""
        if session in self._sessions:
            self._sessions.remove(session)
        self._spawn(self._close(session, end=end))

    async def _close(self, session: PooledSession, *, end: bool = False) -> None:
        client = session.client
        was_open = session.is_open
        session.close()
        if client is None or not was_open:
            return
        if session.listener is not None:
            session.listener.cancel()
            session.listener = None
        try:
            await client.__aexit__(None, None, None)
        except BaseException:
            log.debug("upstream_session.close_failed", server=session.server.name, exc_info=True)
        if end and session.upstream_session_id is not None:
            try:
                await self._transport.end_session(
                    session.server,
                    session.upstream_session_id,
                    session.protocol_version,
                    session.slot.headers,
                )
            except Exception:
                log.info("upstream_session.end_failed", server=session.server.name, exc_info=True)

    def _spawn(self, work: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(work)
        self._closing.add(task)
        task.add_done_callback(self._closing.discard)

    async def _reap(self) -> None:
        while True:
            limits = self._limits()
            await asyncio.sleep(min(max(limits.idle_timeout / 4, 0.05), 5.0))
            try:
                await self._close_idle(self._limits())
            except Exception:
                log.warning("upstream_session.reap_failed", exc_info=True)

    async def _close_idle(self, limits: PoolLimits) -> None:
        """Close sessions idle past the timeout, and idle ones above a lowered cap."""
        now = time.monotonic()
        async with self._lock:
            for session in list(self._sessions):
                if session.evictable and now - session.last_used > limits.idle_timeout:
                    self._evict(session, end=session.ends_upstream_on_eviction)
            for server_name in {session.key.server_name for session in self._sessions}:
                self._trim_to(limits.per_server, _on_server(server_name))
            self._trim_to(limits.total, _everywhere)


def _everywhere(session: PooledSession) -> bool:
    return True


def _on_server(server_name: str) -> Callable[[PooledSession], bool]:
    """Selects the sessions with one server."""

    def on_server(session: PooledSession) -> bool:
        return session.key.server_name == server_name

    return on_server
