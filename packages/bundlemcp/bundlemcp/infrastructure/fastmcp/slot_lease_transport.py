"""A pooled transport that reads each lease's headers from the session's lease slot."""

from typing import Any

from fastmcp import Client

from bundlemcp.application.contracts.upstream.upstream_session_pool import UpstreamLeaseRequest
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.infrastructure.fastmcp.client_factory import LeaseAwareClientFactory
from bundlemcp.infrastructure.fastmcp.lease_slot import LeaseSlot


class SlotLeaseTransport:
    """One transport serves every caller under a key, each request with its own headers.

    Its transport never ends the upstream session as it closes, so the pool
    ends it here, with a ``DELETE``.
    """

    def __init__(self, factory: LeaseAwareClientFactory) -> None:
        self._factory = factory

    def variant(self, request: UpstreamLeaseRequest) -> str | None:
        return None

    def open(
        self, server: McpServer, slot: LeaseSlot, *, continues: bool, handlers: dict[str, Any]
    ) -> Client:
        return self._factory.for_lease(server, slot, auto_initialize=not continues, **handlers)

    async def end_session(
        self,
        server: McpServer,
        session_id: str,
        protocol_version: str | None,
        headers: dict[str, str],
    ) -> None:
        await self._factory.end_session(server, session_id, protocol_version, headers)
