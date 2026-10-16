from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.domain.sessions.upstream_binding import UpstreamBinding
from bundlemcp.domain.sessions.upstream_session_key import UpstreamSessionKey


class UpstreamLeaseRequest(BaseModel):
    """What one request needs from an upstream session, and on whose behalf it asks."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    server: McpServer = Field(description="The upstream server to reach")
    key: UpstreamSessionKey = Field(description="Which pooled sessions may serve the request")
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="The caller-specific headers the request carries: forwarded client headers "
        "and the identity header. Equal for every request under one key",
    )
    credentials: dict[str, str] = Field(
        default_factory=dict,
        description="Credential headers minted or refreshed per request (an upstream OAuth "
        "bearer, a delegated token); sent with this request only",
    )
    handlers: dict[str, Any] = Field(
        default_factory=dict,
        description="The callbacks that relay the server's requests for client input, keyed by "
        "the client keyword they are passed as; a session advertises what it was opened with",
    )
    responses: ResponseLog = Field(
        default_factory=ResponseLog,
        description="Where the unusable HTTP responses the request receives are recorded",
    )
    bound_to: str | None = Field(
        default=None,
        description="The client stream the upstream session is dedicated to — a handshake "
        "session, or a modern client's listen stream; None for a request without one, which "
        "may be served by a shared pooled session",
    )
    binding: UpstreamBinding | None = Field(
        default=None,
        description="The handshake session's binding to this server, continued when it still "
        "matches the key; None when the session has not bound to the server yet",
    )
    fresh: bool = Field(
        default=False,
        description="Open a new upstream session even when the binding names one, as a retry "
        "after that session expired does",
    )


@runtime_checkable
class UpstreamLease(Protocol):
    """One request's exclusive use of an upstream session."""

    @property
    def client(self) -> Any:
        """The protocol SDK's client the request is sent through."""
        ...

    @property
    def binding(self) -> UpstreamBinding | None:
        """The binding that now names the session, for a request bound to a handshake session."""
        ...

    async def subscribe(self, uri: str) -> None:
        """Ask the upstream for updates of one resource on this session, and keep it open.

        A session holding subscriptions is neither evicted nor closed for
        idling: its updates arrive on it between requests.
        """
        ...

    async def unsubscribe(self, uri: str) -> None:
        """Stop the updates of one resource; the session may idle out once it holds none."""
        ...


@runtime_checkable
class UpstreamSessionPool(Protocol):
    """The upstream sessions this replica holds open, handed out one request at a time.

    A lease that ends in an exception gives its session up: the transport may
    be broken, so it is closed rather than reused.
    """

    def lease(self, request: UpstreamLeaseRequest) -> AbstractAsyncContextManager[UpstreamLease]:
        """A session that may serve ``request``, opened if none is free."""
        ...

    async def end(
        self, server: McpServer, binding: UpstreamBinding, headers: dict[str, str]
    ) -> None:
        """End the upstream session a binding names; ``headers`` authenticate the request."""
        ...

    async def invalidate(self, server_name: str) -> None:
        """Close every transport to a server whose configuration changed."""
        ...

    async def invalidate_all(self) -> None:
        """Close every transport, after a gap in which a configuration change may be missed."""
        ...

    async def close(self) -> None:
        """Close everything; the replica is stopping."""
        ...
