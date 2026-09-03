"""The rule that an anonymous endpoint never fronts a per-user upstream.

A server whose upstream OAuth identity is per user needs to know which user is
calling. An endpoint that accepts no credentials cannot say, so the two must
never meet through a bundle. The rule has three edges where it can be broken,
and each mutation asks the policy before it commits.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.models import BundleServer, Endpoint, EndpointAuthMode, McpServer
from bundlemcp.services.errors import ConflictError
from bundlemcp.store import Repository


class PerUserUpstreamPolicy:
    def __init__(self, session: AsyncSession) -> None:
        self._servers = Repository(session, McpServer)
        self._memberships = Repository(session, BundleServer)
        self._endpoints = Repository(session, Endpoint)

    async def ensure_endpoint_allowed(
        self, bundle_id: uuid.UUID, auth_modes: Sequence[EndpointAuthMode]
    ) -> None:
        """An endpoint taking no credentials may not expose a per-user upstream."""
        # UPO-6
        if set(auth_modes) != {EndpointAuthMode.NONE}:
            return
        if await self._bundle_has_per_user_upstream(bundle_id):
            raise ConflictError(
                "a 'none'-auth endpoint cannot expose a bundle with a per_user upstream "
                "server (UPO-6)"
            )

    async def ensure_membership_allowed(self, bundle_id: uuid.UUID, server: McpServer) -> None:
        """A per-user upstream may not join a bundle an anonymous endpoint already exposes."""
        # UPO-6
        if not server.requires_per_user_token:
            return
        if await self._bundle_has_anonymous_endpoint(bundle_id):
            raise ConflictError(
                "a per_user upstream server cannot join a bundle exposed by a 'none'-auth "
                "endpoint (UPO-6)"
            )

    async def ensure_identity_switch_allowed(self, server: McpServer) -> None:
        """A member server may not become per-user while an anonymous endpoint exposes it."""
        # UPO-6
        if not server.requires_per_user_token:
            return
        for membership in await self._memberships.all(BundleServer.server_id == server.id):
            if await self._bundle_has_anonymous_endpoint(membership.bundle_id):
                raise ConflictError(
                    "server cannot switch to per_user while a 'none'-auth endpoint exposes "
                    "one of its bundles (UPO-6)"
                )

    async def _bundle_has_per_user_upstream(self, bundle_id: uuid.UUID) -> bool:
        for membership in await self._memberships.all(BundleServer.bundle_id == bundle_id):
            server = await self._servers.get(membership.server_id)
            if server is not None and server.requires_per_user_token:
                return True
        return False

    async def _bundle_has_anonymous_endpoint(self, bundle_id: uuid.UUID) -> bool:
        endpoints = await self._endpoints.all(Endpoint.bundle_id == bundle_id)
        return any(endpoint.is_anonymous_only for endpoint in endpoints)
