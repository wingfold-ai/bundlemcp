"""Upstream sessions that last one request: the pool with pooling switched off."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.application.contracts.upstream.upstream_client_factory import UpstreamClientFactory
from bundlemcp.application.contracts.upstream.upstream_session_pool import UpstreamLeaseRequest
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.sessions.upstream_binding import UpstreamBinding


class PerCallLease(BaseModel):
    """One request's connection, closed when the request ends."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    client: Any = Field(description="The SDK client the request is sent through")
    binding: UpstreamBinding | None = Field(
        description="What the session's binding records; None for an unbound request"
    )

    async def subscribe(self, uri: str) -> None:
        # nothing outlives the request, so there is nowhere for an update to arrive
        return None

    async def unsubscribe(self, uri: str) -> None:
        return None


class PerCallUpstreamSessions:
    """Opens a connection for each lease and closes it, ending the upstream session, after.

    Nothing is held between requests, so there is nothing to invalidate, and
    a binding records only which server and identity the session used.
    """

    def __init__(self, factory: UpstreamClientFactory) -> None:
        self._factory = factory

    @asynccontextmanager
    async def lease(self, request: UpstreamLeaseRequest) -> AsyncIterator[PerCallLease]:
        client = self._factory(
            request.server,
            {**request.headers, **request.credentials},
            observer=request.responses,
            **request.handlers,
        )
        binding = (
            UpstreamBinding(
                server_name=request.server.name,
                identity_key=request.key.identity_key,
                config_fingerprint=request.key.config_fingerprint,
            )
            if request.bound_to is not None
            else None
        )
        async with client:
            yield PerCallLease(client=client, binding=binding)

    async def end(
        self, server: McpServer, binding: UpstreamBinding, headers: dict[str, str]
    ) -> None:
        return None

    async def invalidate(self, server_name: str) -> None:
        return None

    async def invalidate_all(self) -> None:
        return None

    async def close(self) -> None:
        return None
