"""Cross-resource invariants enforced on mutations (spec 23 UPO-6)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from bundlemcp.models import (
    BundleServer,
    Endpoint,
    EndpointAuthMode,
    IdentityMode,
    McpServer,
    ServerAuthMode,
)


def _is_none_only(auth_modes: list[str]) -> bool:
    return set(auth_modes) == {EndpointAuthMode.NONE}


async def _per_user_upstream_server_ids(db: AsyncSession, bundle_id: uuid.UUID) -> list[uuid.UUID]:
    rows = (
        await db.execute(
            select(McpServer)
            .join(BundleServer, BundleServer.server_id == McpServer.id)
            .where(BundleServer.bundle_id == bundle_id)
        )
    ).scalars()
    return [
        s.id
        for s in rows
        if s.auth_mode == ServerAuthMode.UPSTREAM_OAUTH and s.identity_mode == IdentityMode.PER_USER
    ]


async def endpoint_violates_per_user_upstream(
    db: AsyncSession, bundle_id: uuid.UUID, auth_modes: list[str]
) -> bool:
    """UPO-6: a `none`-only endpoint can't expose a bundle with a per_user upstream."""
    if not _is_none_only(auth_modes):
        return False
    return bool(await _per_user_upstream_server_ids(db, bundle_id))


async def membership_violates_per_user_upstream(
    db: AsyncSession, bundle_id: uuid.UUID, server: McpServer
) -> bool:
    """UPO-6: adding a per_user upstream to a bundle that a none-endpoint exposes."""
    if not (
        server.auth_mode == ServerAuthMode.UPSTREAM_OAUTH
        and server.identity_mode == IdentityMode.PER_USER
    ):
        return False
    endpoints = (
        await db.execute(select(Endpoint).where(Endpoint.bundle_id == bundle_id))
    ).scalars()
    return any(_is_none_only(e.auth_modes) for e in endpoints)


async def identity_switch_violates_per_user_upstream(
    db: AsyncSession, server: McpServer
) -> bool:
    """UPO-6: switching a server to per_user while a none-endpoint exposes its bundle(s)."""
    bundle_ids = (
        await db.execute(
            select(BundleServer.bundle_id).where(BundleServer.server_id == server.id)
        )
    ).scalars()
    for bundle_id in bundle_ids:
        endpoints = (
            await db.execute(select(Endpoint).where(Endpoint.bundle_id == bundle_id))
        ).scalars()
        if any(_is_none_only(e.auth_modes) for e in endpoints):
            return True
    return False
