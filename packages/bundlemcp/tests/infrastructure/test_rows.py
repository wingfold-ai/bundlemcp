"""Row-level constraints the schema enforces: uniqueness and cascades (ARC-16, ARC-17), and the
stored spelling of a server's protocol mode (UPS-10)."""

import pytest
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.protocol_mode import NegotiationMode
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.bundle_server_row import BundleServerRow
from bundlemcp.infrastructure.postgres.rows.bundle_tool_row import BundleToolRow
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory
from sqlalchemy.exc import IntegrityError
from sqlmodel import select


async def _mk_server(db, name="srv") -> McpServerRow:
    server = McpServerRow(name=name, url="http://upstream:8000/mcp")
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return server


async def test_server_name_unique(db):
    await _mk_server(db, "dup")
    db.add(McpServerRow(name="dup", url="http://other:8000/mcp"))
    with pytest.raises(IntegrityError):
        await db.commit()


async def test_tool_unique_per_server_and_cascade_delete(db):
    """ARC-17: deleting a server cascades its tools."""
    server = await _mk_server(db)
    db.add(ToolRow(server_id=server.id, name="t1", schema_hash="h1"))
    await db.commit()

    db.add(ToolRow(server_id=server.id, name="t1", schema_hash="h2"))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()

    await db.delete(server)
    await db.commit()
    assert (await db.execute(select(ToolRow))).scalars().all() == []


async def test_bundle_cascade_deletes_mappings(db):
    """ARC-17: deleting a bundle cascades its mapping rows."""
    server = await _mk_server(db)
    tool = ToolRow(server_id=server.id, name="t1", schema_hash="h")
    bundle = BundleRow(name="b1")
    db.add(tool)
    db.add(bundle)
    await db.commit()

    db.add(BundleServerRow(bundle_id=bundle.id, server_id=server.id))
    db.add(BundleToolRow(bundle_id=bundle.id, tool_id=tool.id, override_name="renamed"))
    await db.commit()

    await db.delete(bundle)
    await db.commit()
    assert (await db.execute(select(BundleServerRow))).scalars().all() == []
    assert (await db.execute(select(BundleToolRow))).scalars().all() == []


async def test_bundle_server_pair_unique(db):
    server = await _mk_server(db)
    bundle = BundleRow(name="b1")
    db.add(bundle)
    await db.commit()

    db.add(BundleServerRow(bundle_id=bundle.id, server_id=server.id))
    await db.commit()
    db.add(BundleServerRow(bundle_id=bundle.id, server_id=server.id))
    with pytest.raises(IntegrityError):
        await db.commit()


async def test_ups10_stored_spelling_stays_readable_one_release_back(engine, redis):
    """UPS-10, DEP-5: a server in 'session' mode is stored as 'legacy', the spelling the
    previous release hands its MCP client, and a stored 'legacy' loads as 'session'; the other
    modes are stored as they are."""
    units = SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis)
    async with units.open() as uow:
        uow.servers.add(McpServer(name="pinned", url="http://p/mcp", protocol_mode="2026-07-28"))
        uow.servers.add(McpServer(name="handshake", url="http://h/mcp", protocol_mode="session"))
        uow.servers.add(McpServer(name="probing", url="http://a/mcp"))
        await uow.commit()
    async with session_factory(engine)() as db:
        stored = {
            row.name: row.protocol_mode
            for row in (await db.execute(select(McpServerRow))).scalars()
        }
    assert stored == {"pinned": "2026-07-28", "handshake": "legacy", "probing": "auto"}
    async with units.open() as uow:
        loaded = await uow.servers.by_name("handshake")
    assert loaded is not None
    assert loaded.protocol_mode == NegotiationMode.SESSION
