"""One upstream session a replica holds a transport to, and the stages of its life."""

import asyncio
import time
from enum import StrEnum

from fastmcp import Client
from mcp_types.version import MODERN_PROTOCOL_VERSIONS
from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.sessions.upstream_binding import UpstreamBinding
from bundlemcp.domain.sessions.upstream_session_key import UpstreamSessionKey
from bundlemcp.infrastructure.fastmcp.lease_slot import LeaseSlot


class SessionState(StrEnum):
    """Where a pooled session is in its life; it only ever moves through ``PooledSession``."""

    LEASED = "leased"
    """A lease holds the session; its transport may not be open yet."""
    IDLE = "idle"
    """Open, with no lease; the next matching request may take it."""
    RETIRING = "retiring"
    """Leased, but its configuration changed or its binding ended: closed when the lease ends."""
    CLOSED = "closed"
    """The transport is closed; the session is never handed out again."""


class IllegalSessionTransition(RuntimeError):
    """A pooled session was asked to move in a way its lifecycle does not allow."""

    def __init__(self, state: SessionState, event: str) -> None:
        super().__init__(f"a {state.value} pooled session cannot {event}")
        self.state = state
        self.event = event


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
        default=None,
        description="The SDK client, once its transport has been opened; None before that",
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
    state: SessionState = Field(
        default=SessionState.LEASED,
        description="Where the session is in its life: leased, idle, retiring or closed. A "
        "session is created for the request that leases it",
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
    def is_open(self) -> bool:
        """Whether the session's transport is open and has not been closed since."""
        return self.client is not None and self.state is not SessionState.CLOSED

    @property
    def is_modern(self) -> bool:
        client = self.client
        return client is not None and client.protocol_version in MODERN_PROTOCOL_VERSIONS

    @property
    def evictable(self) -> bool:
        """Whether closing the session now would take it from nobody: idle, with no updates due."""
        return self.state is SessionState.IDLE and not self.subscriptions

    @property
    def ends_upstream_on_eviction(self) -> bool:
        """Whether evicting the session also ends it upstream.

        A shared session is ended; a bound one only loses its transport, since
        its binding may still be continued elsewhere.
        """
        return self.bound_to is None

    def checkout(self) -> None:
        """Hand the idle session to a new lease."""
        if self.state is not SessionState.IDLE:
            raise IllegalSessionTransition(self.state, "be checked out")
        self.state = SessionState.LEASED

    def release(self) -> None:
        """End the current lease; a retiring or closed session stays as it is."""
        if self.state is SessionState.IDLE:
            raise IllegalSessionTransition(self.state, "be released")
        if self.state is SessionState.LEASED:
            self.state = SessionState.IDLE

    def retire(self) -> None:
        """Mark the session to be closed instead of reused; a closed one stays closed."""
        if self.state is not SessionState.CLOSED:
            self.state = SessionState.RETIRING

    def close(self) -> None:
        """Mark the transport closed, from any state."""
        self.state = SessionState.CLOSED

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
