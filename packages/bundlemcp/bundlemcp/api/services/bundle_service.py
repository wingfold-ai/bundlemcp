"""Bundle composition + tool curation business logic."""

import uuid
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from bundlemcp.api.services.errors import ConflictError, NotFoundError
from bundlemcp.models import Bundle, BundleServer, BundleTool, McpServer, Tool
from bundlemcp.schemas import (
    BundleRead,
    BundleServerUpdate,
    BundleToolUpdate,
    BundleUpsert,
    Page,
)
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
            items=[BundleRead.model_validate(b) for b in rows],
            total=total,
            offset=offset,
            limit=limit,
        )

    async def get(self, name: str) -> BundleRead:
        return BundleRead.model_validate(await self._get(name))

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
        return BundleRead.model_validate(bundle)

    async def delete(self, name: str) -> None:
        bundle = await self._by_name(name)
        if bundle is not None:
            await self._db.delete(bundle)  # DOM-2 cascades mappings + endpoints
            await self._db.commit()
            await self._invalidate(name, "deleted")

    async def set_member(
        self, name: str, server_name: str, body: BundleServerUpdate
    ) -> dict[str, Any]:
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
        return {"bundle": name, "server": server_name, "enabled": mapping.enabled}

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
    ) -> dict[str, Any]:
        """Per-bundle tool curation: enable/disable plus name/metadata overrides."""
        bundle = await self._get(name)
        tool = (
            await self._db.execute(select(Tool).where(Tool.id == tool_id))
        ).scalar_one_or_none()
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
        return {"bundle": name, "tool_id": str(tool_id), "enabled": mapping.enabled}
