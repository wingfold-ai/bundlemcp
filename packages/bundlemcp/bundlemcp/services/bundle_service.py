"""Bundle composition + tool curation business logic."""

# lazy annotations: `list[...]` in the class body would otherwise resolve to
# the `list` method on Python < 3.14
from __future__ import annotations

import uuid

from bundlemcp.models import Bundle, BundleServer, BundleTool, McpServer, PresentedName, Tool
from bundlemcp.schemas import (
    BundleMemberRead,
    BundleMembershipRead,
    BundleRead,
    BundleServerUpdate,
    BundleToolRead,
    BundleToolUpdate,
    BundleUpsert,
    ToolCurationRead,
)
from bundlemcp.services.errors import ConflictError, NotFoundError
from bundlemcp.services.named_resource_service import NamedResourceService
from bundlemcp.services.per_user_upstream_policy import PerUserUpstreamPolicy
from bundlemcp.store import Repository, UnitOfWork
from bundlemcp.store.invalidation import InvalidationEvent


class BundleService(NamedResourceService[Bundle, BundleRead]):
    def __init__(self, uow: UnitOfWork) -> None:
        super().__init__(
            uow, entity=Bundle, read_model=BundleRead, entity_type="bundle", label="bundle"
        )
        self._servers = Repository(uow.session, McpServer)
        self._memberships = Repository(uow.session, BundleServer)
        self._curations = Repository(uow.session, BundleTool)
        self._tools = Repository(uow.session, Tool)
        self._policy = PerUserUpstreamPolicy(uow)

    async def upsert(self, body: BundleUpsert) -> BundleRead:
        bundle = await self._by_name(body.name)
        created = bundle is None
        if bundle is None:
            bundle = Bundle(name=body.name)
        bundle.description = body.description
        return await self._save(bundle, name=body.name, created=created)

    async def _members(self, bundle: Bundle) -> list[tuple[McpServer, BundleServer]]:
        memberships = await self._memberships.all(BundleServer.bundle_id == bundle.id)
        pairs: list[tuple[McpServer, BundleServer]] = []
        for membership in memberships:
            server = await self._servers.get(membership.server_id)
            if server is not None:
                pairs.append((server, membership))
        pairs.sort(key=lambda pair: pair[0].name)
        return pairs

    async def list_members(self, name: str) -> list[BundleMemberRead]:
        bundle = await self._get(name)
        return [
            BundleMemberRead(
                server_id=server.id,
                server_name=server.name,
                server_url=server.url,
                health_status=server.health_status,
                enabled=membership.enabled,
            )
            for server, membership in await self._members(bundle)
        ]

    async def list_tools(self, name: str) -> list[BundleToolRead]:
        """Curation view: every member server's tools with this bundle's overrides."""
        bundle = await self._get(name)
        server_by_id = {server.id: (server, m) for server, m in await self._members(bundle)}
        if not server_by_id:
            return []
        curation = {
            c.tool_id: c for c in await self._curations.all(BundleTool.bundle_id == bundle.id)
        }
        tools = await self._tools.all(
            Tool.server_id.in_(server_by_id),  # type: ignore[attr-defined]
            order_by=(Tool.name,),
        )
        out = [
            self._tool_read(tool, *server_by_id[tool.server_id], curation.get(tool.id))
            for tool in tools
        ]
        out.sort(key=lambda t: (t.server_name, t.name))
        return out

    @staticmethod
    def _tool_read(
        tool: Tool, server: McpServer, membership: BundleServer, curation: BundleTool | None
    ) -> BundleToolRead:
        override_name = curation.override_name if curation else None
        return BundleToolRead(
            tool_id=tool.id,
            server_name=server.name,
            name=tool.name,
            title=tool.title,
            description=tool.description,
            member_enabled=membership.enabled,
            enabled=curation.enabled if curation is not None else True,
            presented_name=PresentedName.for_tool(server.name, tool.name, override_name),
            override_name=override_name,
            override_title=curation.override_title if curation else None,
            override_description=curation.override_description if curation else None,
        )

    async def _membership(self, bundle: Bundle, server: McpServer) -> BundleServer | None:
        return await self._memberships.one(
            BundleServer.bundle_id == bundle.id, BundleServer.server_id == server.id
        )

    async def set_member(
        self, name: str, server_name: str, body: BundleServerUpdate
    ) -> BundleMembershipRead:
        """Add a member server or toggle its enabled flag; upsert semantics."""
        bundle = await self._get(name)
        server = await self._servers.by_name(server_name)
        if server is None:
            raise NotFoundError("server not found")
        await self._policy.ensure_membership_allowed(bundle.id, server)
        membership = await self._membership(bundle, server)
        if membership is None:
            membership = BundleServer(bundle_id=bundle.id, server_id=server.id)
        membership.enabled = body.enabled
        self._memberships.add(membership)
        self._invalidate(name)
        await self._uow.commit()
        return BundleMembershipRead(bundle=name, server=server_name, enabled=membership.enabled)

    async def remove_member(self, name: str, server_name: str) -> None:
        bundle = await self._get(name)
        server = await self._servers.by_name(server_name)
        if server is None:
            return
        membership = await self._membership(bundle, server)
        if membership is None:
            return
        await self._memberships.delete(membership)
        self._invalidate(name)
        await self._uow.commit()

    async def curate_tool(
        self, name: str, tool_id: uuid.UUID, body: BundleToolUpdate
    ) -> ToolCurationRead:
        """Per-bundle tool curation: enable/disable plus name/metadata overrides."""
        bundle = await self._get(name)
        tool = await self._tools.get(tool_id)
        if tool is None:
            raise NotFoundError("tool not found")
        if body.override_name is not None:
            await self._ensure_override_name_free(bundle, tool_id, body.override_name)

        curation = await self._curations.one(
            BundleTool.bundle_id == bundle.id, BundleTool.tool_id == tool_id
        )
        if curation is None:
            curation = BundleTool(bundle_id=bundle.id, tool_id=tool_id)
        curation.enabled = body.enabled
        curation.override_name = body.override_name
        curation.override_title = body.override_title
        curation.override_description = body.override_description
        curation.override_annotations = body.override_annotations
        self._curations.add(curation)
        self._uow.invalidate(
            InvalidationEvent(entity_type="bundle_tool", key=str(tool_id), action="updated")
        )
        self._invalidate(name)
        await self._uow.commit()

        server = await self._servers.get(tool.server_id)
        server_name = server.name if server is not None else ""
        return ToolCurationRead(
            bundle=name,
            tool_id=tool_id,
            enabled=curation.enabled,
            presented_name=PresentedName.for_tool(server_name, tool.name, curation.override_name),
            override_name=curation.override_name,
            override_title=curation.override_title,
            override_description=curation.override_description,
            override_annotations=curation.override_annotations,
        )

    async def _ensure_override_name_free(
        self, bundle: Bundle, tool_id: uuid.UUID, override_name: str
    ) -> None:
        # TM-3: override names unique within the bundle vs other overrides
        clash = await self._curations.one(
            BundleTool.bundle_id == bundle.id,
            BundleTool.override_name == override_name,
            BundleTool.tool_id != tool_id,
        )
        if clash is not None:
            raise ConflictError("override_name already used in this bundle (TM-3)")
