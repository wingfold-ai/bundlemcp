"""A pooled transport that keeps the headers it was built with."""

import hashlib
import json
from typing import Any

from fastmcp import Client

from bundlemcp.application.contracts.upstream.upstream_client_factory import UpstreamClientFactory
from bundlemcp.application.contracts.upstream.upstream_session_pool import UpstreamLeaseRequest
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.infrastructure.fastmcp.lease_slot import LeaseSlot, SlotResponseLog


class FixedHeaderLeaseTransport:
    """A plain client factory's transport: its headers are fixed when it is built.

    The headers therefore become part of what a session must match, and the
    pool never ends such a session itself; its transport does that as it closes.
    """

    def __init__(self, factory: UpstreamClientFactory) -> None:
        self._factory = factory

    def variant(self, request: UpstreamLeaseRequest) -> str | None:
        material = sorted({**request.headers, **request.credentials}.items())
        return hashlib.sha256(json.dumps(material).encode()).hexdigest()

    def open(
        self, server: McpServer, slot: LeaseSlot, *, continues: bool, handlers: dict[str, Any]
    ) -> Client:
        return self._factory(server, slot.headers, observer=SlotResponseLog(slot), **handlers)

    async def end_session(
        self,
        server: McpServer,
        session_id: str,
        protocol_version: str | None,
        headers: dict[str, str],
    ) -> None:
        return None
