"""Bundle composition + tool curation business logic."""

# lazy annotations: `list[...]` in the class body would otherwise resolve to
# the `list` method on Python < 3.14
from __future__ import annotations

import uuid

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from bundlemcp.models import Bundle, BundleServer, BundleTool, McpServer, PresentedName, Tool
from bundlemcp.schemas import (
    BundleMemberRead,
    BundleMembershipRead,
    BundleRead,
    BundleServerUpdate,
    BundleToolRead,
    BundleToolUpdate,
    BundleUpsert,
    Page,
    ToolCurationRead,
)
from bundlemcp.services.errors import ConflictError, NotFoundError
from bundlemcp.store.invalidation import InvalidationEvent, publish_invalidation


class BundleService:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self._db = db
        self._redis = redis

    async def _by_name(self, name: str) -> Bundle | None:
        return (
            await self._db.execute(select(Bundle).where(Bundle.name == name))
        ).scalar_one_or_none()

    async def _get(self, name: str) -> Bundle:
        bundle = await self._by_name(name)
        if bundle is None:
            raise NotFoundError("bundle not found")
        return bundle

    async def _server_by_name(self, name: str) -> McpServer | None:
        return (
            await self._db.execute(select(McpServer).where(McpServer.name == name))
        ).scalar_one_or_none()

    async def _invalidate(self, name: str, action: str = "updated") -> None:
        await publish_invalidation(
            self._redis, InvalidationEvent(entity_type="bundle", key=name, action=action)
        )

    async def list(self, *, offset: int, limit: int) -> Page[BundleRead]:
        total = (await self._db.execute(select(func.count()).select_from(Bundle))).scalar_one()
        rows = (
            await self._db.execute(
                select(Bundle).order_by(Bundle.created_at, Bundle.id).offset(offset).limit(limit)
            )
        ).scalars()
        return Page(
            items=[BundleRead.from_entity(b) for b in rows],
            total=total,
            offset=offset,
            limit=limit,
        )

    async def get(self, name: str) -> BundleRead:
        return BundleRead.from_entity(await self._get(name))

    async def upsert(self, body: BundleUpsert) -> BundleRead:
        bundle = await self._by_name(body.name)
        created = bundle is None
        if bundle is None:
            bundle = Bundle(name=body.name)
        bundle.description = body.description
        self._db.add(bundle)
        await self._db.commit()
        await self._db.refresh(bundle)
        await self._invalidate(body.name, "created" if created else "updated")
        return BundleRead.from_entity(bundle)

    async def delete(self, name: str) -> None:
        bundle = await self._by_name(name)
        if bundle is not None:
            await self._db.delete(bundle)  # DOM-2 cascades mappings + endpoints
            await self._db.commit()
            await self._invalidate(name, "deleted")

    async def list_members(self, name: str) -> list[BundleMemberRead]:
        bundle = await self._get(name)
        rows = (
            (
                await self._db.execute(
                    select(McpServer, BundleServer)
                    .join(BundleServer, BundleServer.server_id == McpServer.id)
                    .where(BundleServer.bundle_id == bundle.id)
                    .order_by(McpServer.name)
                )
            )
            .tuples()
            .all()
        )
        return [
            BundleMemberRead(
                server_id=srv.id,
                server_name=srv.name,
                server_url=srv.url,
                health_status=srv.health_status,
                enabled=mapping.enabled,
            )
            for srv, mapping in rows
        ]

    async def list_tools(self, name: str) -> list[BundleToolRead]:
        """Curation view: every member server's tools with this bundle's overrides."""
        bundle = await self._get(name)
        members = (
            (
                await self._db.execute(
                    select(McpServer, BundleServer)
                    .join(BundleServer, BundleServer.server_id == McpServer.id)
                    .where(BundleServer.bundle_id == bundle.id)
                )
            )
            .tuples()
            .all()
        )
        server_by_id = {srv.id: (srv, mapping) for srv, mapping in members}
        if not server_by_id:
            return []
        curation = {
            bt.tool_id: bt
            for bt in (
                await self._db.execute(select(BundleTool).where(BundleTool.bundle_id == bundle.id))
            ).scalars()
        }
        tools = (
            await self._db.execute(
                select(Tool)
                .where(Tool.server_id.in_(server_by_id))  # type: ignore[attr-defined]
                .order_by(Tool.name)
            )
        ).scalars()
        out: list[BundleToolRead] = []
        for tool in tools:
            srv, mapping = server_by_id[tool.server_id]
            cur = curation.get(tool.id)
            out.append(
                BundleToolRead(
                    tool_id=tool.id,
                    server_name=srv.name,
                    name=tool.name,
                    title=tool.title,
                    description=tool.description,
                    member_enabled=mapping.enabled,
                    enabled=cur.enabled if cur is not None else True,
                    presented_name=PresentedName.for_tool(
                        srv.name, tool.name, cur.override_name if cur else None
                    ),
                    override_name=cur.override_name if cur else None,
                    override_title=cur.override_title if cur else None,
                    override_description=cur.override_description if cur else None,
                )
            )
        out.sort(key=lambda t: (t.server_name, t.name))
        return out

    async def set_member(
        self, name: str, server_name: str, body: BundleServerUpdate
    ) -> BundleMembershipRead:
        """Add a member server or toggle its enabled flag; upsert semantics."""
        bundle = await self._get(name)
        server = await self._server_by_name(server_name)
        if server is None:
            raise NotFoundError("server not found")
        mapping = (
            await self._db.execute(
                select(BundleServer).where(
                    BundleServer.bundle_id == bundle.id, BundleServer.server_id == server.id
                )
            )
        ).scalar_one_or_none()
        if mapping is None:
            mapping = BundleServer(bundle_id=bundle.id, server_id=server.id)
        mapping.enabled = body.enabled
        self._db.add(mapping)
        await self._db.commit()
        await self._invalidate(name)
        return BundleMembershipRead(bundle=name, server=server_name, enabled=mapping.enabled)

    async def remove_member(self, name: str, server_name: str) -> None:
        bundle = await self._get(name)
        server = await self._server_by_name(server_name)
        if server is None:
            return
        mapping = (
            await self._db.execute(
                select(BundleServer).where(
                    BundleServer.bundle_id == bundle.id, BundleServer.server_id == server.id
                )
            )
        ).scalar_one_or_none()
        if mapping is not None:
            await self._db.delete(mapping)
            await self._db.commit()
            await self._invalidate(name)

    async def curate_tool(
        self, name: str, tool_id: uuid.UUID, body: BundleToolUpdate
    ) -> ToolCurationRead:
        """Per-bundle tool curation: enable/disable plus name/metadata overrides."""
        bundle = await self._get(name)
        tool = (await self._db.execute(select(Tool).where(Tool.id == tool_id))).scalar_one_or_none()
        if tool is None:
            raise NotFoundError("tool not found")

        if body.override_name is not None:
            # TM-3: override names unique within the bundle vs other overrides
            clash = (
                await self._db.execute(
                    select(BundleTool).where(
                        BundleTool.bundle_id == bundle.id,
                        BundleTool.override_name == body.override_name,
                        BundleTool.tool_id != tool_id,
                    )
                )
            ).scalar_one_or_none()
            if clash is not None:
                raise ConflictError("override_name already used in this bundle (TM-3)")

        mapping = (
            await self._db.execute(
                select(BundleTool).where(
                    BundleTool.bundle_id == bundle.id, BundleTool.tool_id == tool_id
                )
            )
        ).scalar_one_or_none()
        if mapping is None:
            mapping = BundleTool(bundle_id=bundle.id, tool_id=tool_id)
        mapping.enabled = body.enabled
        mapping.override_name = body.override_name
        mapping.override_title = body.override_title
        mapping.override_description = body.override_description
        mapping.override_annotations = body.override_annotations
        self._db.add(mapping)
        await self._db.commit()
        await publish_invalidation(
            self._redis,
            InvalidationEvent(entity_type="bundle_tool", key=str(tool_id), action="updated"),
        )
        await self._invalidate(name)
        server = (
            await self._db.execute(select(McpServer).where(McpServer.id == tool.server_id))
        ).scalar_one()
        return ToolCurationRead(
            bundle=name,
            tool_id=tool_id,
            enabled=mapping.enabled,
            presented_name=PresentedName.for_tool(server.name, tool.name, mapping.override_name),
            override_name=mapping.override_name,
            override_title=mapping.override_title,
            override_description=mapping.override_description,
            override_annotations=mapping.override_annotations,
        )
