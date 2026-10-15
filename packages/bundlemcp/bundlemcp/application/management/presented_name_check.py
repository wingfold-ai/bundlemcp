"""Asking the presented-name rule at each write that can change a bundle's tool names."""

import uuid

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import ConflictError
from bundlemcp.domain.bundles.bundle import Bundle
from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.domain.bundles.presented_name_policy import NameCollision, PresentedNamePolicy
from bundlemcp.domain.servers.mcp_server import McpServer


class PresentedNameCheck:
    """Loads a bundle's member tools and raises when a write would present one name twice.

    The three writes that change presented names are an override name, a new
    member and a renamed member upstream; each is checked as if it had
    already happened.
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def ensure_override_allowed(self, bundle: Bundle, curation: BundleTool) -> None:
        """An override name may equal neither another override nor another tool's prefixed name."""
        policy = await self._policy(bundle, curation=curation)
        self._refuse(policy.collisions({curation.tool_id}))

    async def ensure_member_allowed(self, bundle: Bundle, server: McpServer) -> None:
        """A new member's prefixed names may not equal an existing override name."""
        policy = await self._policy(bundle, joining=server)
        self._refuse(policy.collisions(await self._tool_ids(server)))

    async def ensure_rename_allowed(self, server: McpServer, new_name: str) -> None:
        """A renamed member's prefixed names may not equal an override in any of its bundles."""
        renamed = server.model_copy(update={"name": new_name})
        tool_ids = await self._tool_ids(server)
        for membership in await self._uow.memberships.for_server(server.id):
            bundle = await self._uow.bundles.get(membership.bundle_id)
            if bundle is None:
                continue
            policy = await self._policy(bundle, joining=renamed)
            if collisions := policy.collisions(tool_ids):
                raise ConflictError(
                    f"renaming the upstream to '{new_name}' collides in bundle "
                    f"'{bundle.name}': {collisions[0].message} (BND-14)"
                )

    async def _tool_ids(self, server: McpServer) -> set[uuid.UUID]:
        return {tool.id for tool in await self._uow.tools.for_server(server.id)}

    async def _policy(
        self,
        bundle: Bundle,
        *,
        joining: McpServer | None = None,
        curation: BundleTool | None = None,
    ) -> PresentedNamePolicy:
        """The bundle's names, with ``joining`` as a member and ``curation`` in force."""
        memberships = await self._uow.memberships.for_bundle(bundle.id)
        servers = {
            s.id: s for s in await self._uow.servers.by_ids(m.server_id for m in memberships)
        }
        if joining is not None:
            servers[joining.id] = joining
        curations = {c.tool_id: c for c in await self._uow.curations.for_bundle(bundle.id)}
        if curation is not None:
            curations[curation.tool_id] = curation
        return PresentedNamePolicy(
            servers=servers,
            tools=await self._uow.tools.for_servers(servers),
            curations=curations,
        )

    @staticmethod
    def _refuse(collisions: list[NameCollision]) -> None:
        if collisions:
            raise ConflictError(f"presented name already in use: {collisions[0].message} (BND-14)")
