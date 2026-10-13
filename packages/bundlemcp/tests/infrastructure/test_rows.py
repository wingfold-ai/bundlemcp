"""Row-level constraints the schema enforces: uniqueness and cascades (ARC-16, ARC-17)."""

import pytest
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.bundle_server_row import BundleServerRow
from bundlemcp.infrastructure.postgres.rows.bundle_tool_row import BundleToolRow
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow
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
