"""Asking the per-user-upstream rule at each of the three edges where it can be broken."""

import uuid
from collections.abc import Sequence

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import ConflictError
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.policies.per_user_upstream_policy import PerUserUpstreamPolicy
from bundlemcp.domain.servers.mcp_server import McpServer


class PerUserUpstreamCheck:
    """Loads what the rule needs to see and raises when a mutation would break it."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def ensure_endpoint_allowed(
        self, bundle_id: uuid.UUID, auth_modes: Sequence[EndpointAuthMode]
    ) -> None:
        """An endpoint taking no credentials may not expose a per-user upstream."""
        # UPO-6
        members = await self._members(bundle_id)
        if not PerUserUpstreamPolicy.endpoint_may_expose(auth_modes, members):
            raise ConflictError(
                "a 'none'-auth endpoint cannot expose a bundle with a per_user upstream "
                "server (UPO-6)"
            )

    async def ensure_membership_allowed(self, bundle_id: uuid.UUID, server: McpServer) -> None:
        """A per-user upstream may not join a bundle an anonymous endpoint already exposes."""
        # UPO-6
        endpoints = await self._uow.endpoints.for_bundle(bundle_id)
        if not PerUserUpstreamPolicy.server_may_join(server, endpoints):
            raise ConflictError(
                "a per_user upstream server cannot join a bundle exposed by a 'none'-auth "
                "endpoint (UPO-6)"
            )

    async def ensure_identity_switch_allowed(self, server: McpServer) -> None:
        """A member server may not become per-user while an anonymous endpoint exposes it."""
        # UPO-6
        for membership in await self._uow.memberships.for_server(server.id):
            endpoints = await self._uow.endpoints.for_bundle(membership.bundle_id)
            if not PerUserUpstreamPolicy.server_may_join(server, endpoints):
                raise ConflictError(
                    "server cannot switch to per_user while a 'none'-auth endpoint exposes "
                    "one of its bundles (UPO-6)"
                )

    async def _members(self, bundle_id: uuid.UUID) -> list[McpServer]:
        servers = []
        for membership in await self._uow.memberships.for_bundle(bundle_id):
            server = await self._uow.servers.get(membership.server_id)
            if server is not None:
                servers.append(server)
        return servers
