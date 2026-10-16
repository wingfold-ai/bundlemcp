"""Upstream MCP sessions held open on this replica and handed out one request at a time."""

import asyncio
import hashlib
import json
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastmcp import Client
from mcp import types as mcp_types
from mcp.client.subscriptions import (
    PromptsListChanged,
    ResourcesListChanged,
    ResourceUpdated,
    ToolsListChanged,
    listen,
)
from mcp_types.version import MODERN_PROTOCOL_VERSIONS
from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.application.contracts.upstream.upstream_client_factory import UpstreamClientFactory
from bundlemcp.application.contracts.upstream.upstream_notification_sink import (
    UpstreamNotificationSink,
)
from bundlemcp.application.contracts.upstream.upstream_session_pool import UpstreamLeaseRequest
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.sessions.upstream_binding import UpstreamBinding
from bundlemcp.domain.sessions.upstream_session_key import UpstreamSessionKey
from bundlemcp.infrastructure.fastmcp.client_factory import LeaseAwareClientFactory
from bundlemcp.infrastructure.fastmcp.lease_slot import LeaseSlot, SlotResponseLog

log = structlog.get_logger(__name__)

# the client keywords whose presence changes what a session advertises at initialize
RELAY_KEYWORDS = frozenset({"elicitation_handler", "sampling_handler", "roots"})
LOG_HANDLER = "log_handler"

# notifications an upstream sends that are about the server, not about a request
SERVER_NOTIFICATIONS = (
    mcp_types.ToolListChangedNotification,
    mcp_types.PromptListChangedNotification,
    mcp_types.ResourceListChangedNotification,
    mcp_types.ResourceUpdatedNotification,
)


# what a modern upstream's listen stream reports, as the notification a handshake one would send
_LISTEN_EVENTS = {
    ToolsListChanged: "notifications/tools/list_changed",
    PromptsListChanged: "notifications/prompts/list_changed",
    ResourcesListChanged: "notifications/resources/list_changed",
}
LISTEN_RETRY_SECONDS = 1.0


class PoolLimits(BaseModel):
    """The caps and idle timeout in force at one checkout."""

    model_config = ConfigDict(frozen=True)

    total: int = Field(ge=1, description="Upstream sessions this replica holds open at most")
    per_server: int = Field(ge=1, description="Upstream sessions held open per server at most")
    idle_timeout: float = Field(
        gt=0, description="Seconds an unused session is kept before it is closed"
    )


class PooledSession(BaseModel):
    """One upstream session this replica holds a transport to."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    server: McpServer = Field(description="The server the session is with, as configured")
    key: UpstreamSessionKey = Field(description="Which requests the session may serve")
    relay: frozenset[str] = Field(
        description="The relay callbacks the session was opened with, which it advertised"
    )
    variant: str | None = Field(
        description="Digest of the headers fixed into a transport that cannot take them per "
        "request; None for a transport that takes them per request"
    )
    bound_to: str | None = Field(
        description="The handshake session the upstream session is dedicated to; None for a "
        "session shared between requests"
    )
    slot: LeaseSlot = Field(description="What the current lease puts on the wire")
    client: Client | None = Field(
        default=None, description="The SDK client, once the transport is built"
    )
    upstream_session_id: str | None = Field(
        default=None, description="Session id the upstream issued; None for one without sessions"
    )
    protocol_version: str | None = Field(
        default=None, description="MCP revision the upstream session negotiated"
    )
    pooled: bool = Field(
        default=True,
        description="Whether the session counts toward the caps and is kept after its lease; a "
        "session opened past a cap serves one request and is closed",
    )
    in_use: bool = Field(default=True, description="Whether a lease holds the session now")
    connected: bool = Field(default=False, description="Whether the transport has been opened")
    stale: bool = Field(
        default=False,
        description="Whether the server's configuration changed since the session was opened, "
        "so it is closed instead of reused",
    )
    last_used: float = Field(
        default_factory=time.monotonic, description="When a lease last released the session"
    )
    subscriptions: set[str] = Field(
        default_factory=set,
        description="Resource URIs the session is subscribed to; while there are any it is "
        "kept open, since their updates arrive on it",
    )
    listener: asyncio.Task[None] | None = Field(
        default=None,
        description="The standing subscriptions/listen of a session with a modern upstream, "
        "which has no stream of its own between requests",
    )

    @property
    def is_modern(self) -> bool:
        client = self.client
        return client is not None and client.protocol_version in MODERN_PROTOCOL_VERSIONS

    @property
    def evictable(self) -> bool:
        return not self.in_use and not self.subscriptions

    def serves(
        self,
        key: UpstreamSessionKey,
        relay: frozenset[str],
        variant: str | None,
        bound_to: str | None,
    ) -> bool:
        return (
            self.key == key
            and self.relay == relay
            and self.variant == variant
            and self.bound_to == bound_to
        )

    def binding(self) -> UpstreamBinding:
        return UpstreamBinding(
            server_name=self.server.name,
            upstream_session_id=self.upstream_session_id,
            identity_key=self.key.identity_key,
            protocol_version=self.protocol_version,
            config_fingerprint=self.key.config_fingerprint,
        )


class PooledLease(BaseModel):
    """One request's use of a pooled session."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    client: Any = Field(description="The SDK client the request is sent through")
    binding: UpstreamBinding | None = Field(
        description="The binding that now names the session; None for an unbound request"
    )
    session: PooledSession = Field(exclude=True, description="The session the lease is on")
    pool: Any = Field(exclude=True, description="The pool the session belongs to")

    async def subscribe(self, uri: str) -> None:
        if not self.session.is_modern:
            await self.client.session.subscribe_resource(uri)
        self.session.subscriptions.add(uri)
        self.pool.relisten(self.session)

    async def unsubscribe(self, uri: str) -> None:
        # the subscription may have been made through another replica's transport
        self.session.subscriptions.discard(uri)
        if not self.session.is_modern:
            await self.client.session.unsubscribe_resource(uri)
        self.pool.relisten(self.session)


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
        self._factory = factory
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
            if not session.connected:
                await self._connect(session)
            yield PooledLease(
                client=session.client,
                binding=session.binding() if session.bound_to is not None else None,
                session=session,
                pool=self,
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
                session.stale = True
                if not session.in_use:
                    self._sessions.remove(session)
                    self._spawn(self._close(session))
        if isinstance(self._factory, LeaseAwareClientFactory):
            try:
                await self._factory.end_session(
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
                session.stale = True
                if not session.in_use:
                    self._sessions.remove(session)
                    self._spawn(self._close(session, end=True))

    async def _checkout(self, request: UpstreamLeaseRequest) -> PooledSession:
        relay = frozenset(name for name in request.handlers if name in RELAY_KEYWORDS)
        variant = self._variant(request)
        limits = self._limits()
        async with self._lock:
            wanted = self._continued_id(request)
            for session in list(self._sessions):
                if (
                    session.in_use
                    or session.stale
                    or not session.serves(request.key, relay, variant, request.bound_to)
                ):
                    continue
                if request.fresh:
                    # the session a retry gave up on had expired; its idle siblings likely too
                    self._sessions.remove(session)
                    self._spawn(self._close(session))
                elif wanted is None or session.upstream_session_id == wanted:
                    session.in_use = True
                    return session
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

    def _variant(self, request: UpstreamLeaseRequest) -> str | None:
        if isinstance(self._factory, LeaseAwareClientFactory):
            return None
        # this transport keeps the headers it was built with, so they are part of the key
        material = sorted({**request.headers, **request.credentials}.items())
        return hashlib.sha256(json.dumps(material).encode()).hexdigest()

    def _make_room(self, server_name: str, limits: PoolLimits) -> bool:
        """Evict idle sessions until one more fits under both caps; False when none can go."""
        while True:
            on_server = [s for s in self._sessions if s.key.server_name == server_name]
            if len(self._sessions) < limits.total and len(on_server) < limits.per_server:
                return True
            scope = self._sessions if len(self._sessions) >= limits.total else on_server
            victim = self._eviction_candidate(scope)
            if victim is None:
                return False
            self._sessions.remove(victim)
            self._spawn(self._close(victim, end=victim.bound_to is None))

    @staticmethod
    def _eviction_candidate(sessions: list[PooledSession]) -> PooledSession | None:
        idle = [session for session in sessions if session.evictable]
        if not idle:
            return None
        # identity-free sessions go first: any request can open another one
        return min(idle, key=lambda s: (not s.key.is_shared, s.last_used))

    async def _connect(self, session: PooledSession) -> None:
        handlers = self._handlers(session)
        if isinstance(self._factory, LeaseAwareClientFactory):
            client = self._factory.for_lease(
                session.server,
                session.slot,
                auto_initialize=session.upstream_session_id is None,
                **handlers,
            )
        else:
            client = self._factory(
                session.server,
                session.slot.headers,
                observer=SlotResponseLog(session.slot),
                **handlers,
            )
        session.client = client
        await client.__aenter__()
        session.connected = True
        if session.upstream_session_id is None:
            transport_session = getattr(client.transport, "get_session_id", None)
            session.upstream_session_id = transport_session() if transport_session else None
            session.protocol_version = client.protocol_version
        self.relisten(session)

    def relisten(self, session: PooledSession) -> None:
        """(Re)open a modern session's standing listen for what it should now hear."""
        if session.listener is not None:
            session.listener.cancel()
            session.listener = None
        if session.connected and session.is_modern and self._listen_filter(session):
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
        assert session.client is not None
        while session.connected:
            try:
                async with listen(session.client.session, **self._listen_filter(session)) as events:
                    async for event in events:
                        await self._notify(session, self._listened(event))
            except asyncio.CancelledError:
                raise
            except Exception:
                log.debug("upstream_session.listen_lost", server=session.server.name, exc_info=True)
            await asyncio.sleep(LISTEN_RETRY_SECONDS)

    @staticmethod
    def _listened(event: Any) -> dict[str, Any]:
        if isinstance(event, ResourceUpdated):
            return {"method": "notifications/resources/updated", "params": {"uri": event.uri}}
        return {"method": _LISTEN_EVENTS[type(event)]}

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
                await self._notify(
                    session,
                    {
                        "jsonrpc": "2.0",
                        "method": "notifications/message",
                        "params": message.model_dump(by_alias=True, mode="json", exclude_none=True),
                    },
                )

        async def message_handler(message: Any) -> None:
            if isinstance(message, SERVER_NOTIFICATIONS):
                await self._notify(
                    session, message.model_dump(by_alias=True, mode="json", exclude_none=True)
                )

        handlers[LOG_HANDLER] = log_handler
        handlers["message_handler"] = message_handler
        return handlers

    async def _notify(self, session: PooledSession, notification: dict[str, Any]) -> None:
        notification.setdefault("jsonrpc", "2.0")
        try:
            await self._notifications.received(
                session.server, notification, bound_to=session.bound_to
            )
        except Exception:
            log.warning(
                "upstream_session.notification_failed",
                server=session.server.name,
                method=notification.get("method"),
                exc_info=True,
            )

    async def _release(self, session: PooledSession) -> None:
        session.slot.finish()
        async with self._lock:
            session.in_use = False
            session.last_used = time.monotonic()
            if not session.pooled:
                self._spawn(self._close(session, end=True))
            elif session.stale:
                if session in self._sessions:
                    self._sessions.remove(session)
                self._spawn(self._close(session, end=True))

    def _discard(self, session: PooledSession, *, end: bool) -> None:
        session.slot.finish()
        if session in self._sessions:
            self._sessions.remove(session)
        self._spawn(self._close(session, end=end))

    async def _close(self, session: PooledSession, *, end: bool = False) -> None:
        client = session.client
        if client is None or not session.connected:
            return
        session.connected = False
        if session.listener is not None:
            session.listener.cancel()
            session.listener = None
        try:
            await client.__aexit__(None, None, None)
        except BaseException:
            log.debug("upstream_session.close_failed", server=session.server.name, exc_info=True)
        if end and session.upstream_session_id is not None:
            if isinstance(self._factory, LeaseAwareClientFactory):
                try:
                    await self._factory.end_session(
                        session.server,
                        session.upstream_session_id,
                        session.protocol_version,
                        session.slot.headers,
                    )
                except Exception:
                    log.info(
                        "upstream_session.end_failed", server=session.server.name, exc_info=True
                    )

    def _spawn(self, work: Any) -> None:
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
                    self._sessions.remove(session)
                    self._spawn(self._close(session, end=session.bound_to is None))
            for server_name in {session.key.server_name for session in self._sessions}:
                while True:
                    on_server = [s for s in self._sessions if s.key.server_name == server_name]
                    if len(on_server) <= limits.per_server:
                        break
                    victim = self._eviction_candidate(on_server)
                    if victim is None:
                        break
                    self._sessions.remove(victim)
                    self._spawn(self._close(victim, end=victim.bound_to is None))
            while len(self._sessions) > limits.total:
                victim = self._eviction_candidate(self._sessions)
                if victim is None:
                    break
                self._sessions.remove(victim)
                self._spawn(self._close(victim, end=victim.bound_to is None))
