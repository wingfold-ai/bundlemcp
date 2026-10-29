"""How a pooled session's transport takes each lease's headers, and how its session is ended."""

from typing import Any, Protocol, runtime_checkable

from fastmcp import Client

from bundlemcp.application.contracts.upstream.upstream_client_factory import UpstreamClientFactory
from bundlemcp.application.contracts.upstream.upstream_session_pool import UpstreamLeaseRequest
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.infrastructure.fastmcp.client_factory import LeaseAwareClientFactory
from bundlemcp.infrastructure.fastmcp.fixed_header_lease_transport import (
    FixedHeaderLeaseTransport,
)
from bundlemcp.infrastructure.fastmcp.lease_slot import LeaseSlot
from bundlemcp.infrastructure.fastmcp.slot_lease_transport import SlotLeaseTransport


@runtime_checkable
class LeaseTransport(Protocol):
    """The part of pooling that depends on what the client factory can build."""

    def variant(self, request: UpstreamLeaseRequest) -> str | None:
        """What besides the key a session must match to serve ``request``; None for nothing."""
        ...

    def open(
        self, server: McpServer, slot: LeaseSlot, *, continues: bool, handlers: dict[str, Any]
    ) -> Client:
        """A client for a new session; ``continues`` when it goes on with an existing one."""
        ...

    async def end_session(
        self,
        server: McpServer,
        session_id: str,
        protocol_version: str | None,
        headers: dict[str, str],
    ) -> None:
        """End one upstream session, where this transport leaves that to the pool."""
        ...


def lease_transport_for(factory: UpstreamClientFactory) -> LeaseTransport:
    """The lease transport a factory supports: per-lease headers when it can build them."""
    if isinstance(factory, LeaseAwareClientFactory):
        return SlotLeaseTransport(factory)
    return FixedHeaderLeaseTransport(factory)
