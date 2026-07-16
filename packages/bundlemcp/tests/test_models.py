"""Entity/constraint tests (spec 02: DOM-1, DOM-2)."""

import pytest
from bundlemcp.models import Bundle, BundleServer, BundleTool, McpServer, Tool
from sqlalchemy.exc import IntegrityError
from sqlmodel import select


async def _mk_server(db, name="srv") -> McpServer:
    server = McpServer(name=name, url="http://upstream:8000/mcp")
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return server


async def test_server_name_unique(db):
    await _mk_server(db, "dup")
    db.add(McpServer(name="dup", url="http://other:8000/mcp"))
    with pytest.raises(IntegrityError):
        await db.commit()


async def test_tool_unique_per_server_and_cascade_delete(db):
    """DOM-2: deleting a server cascades its tools."""
    server = await _mk_server(db)
    db.add(Tool(server_id=server.id, name="t1", schema_hash="h1"))
    await db.commit()

    db.add(Tool(server_id=server.id, name="t1", schema_hash="h2"))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()

    await db.delete(server)
    await db.commit()
    assert (await db.execute(select(Tool))).scalars().all() == []


async def test_bundle_cascade_deletes_mappings(db):
    """DOM-2: deleting a bundle cascades its mapping rows."""
    server = await _mk_server(db)
    tool = Tool(server_id=server.id, name="t1", schema_hash="h")
    bundle = Bundle(name="b1")
    db.add(tool)
    db.add(bundle)
    await db.commit()

    db.add(BundleServer(bundle_id=bundle.id, server_id=server.id))
    db.add(BundleTool(bundle_id=bundle.id, tool_id=tool.id, override_name="renamed"))
    await db.commit()

    await db.delete(bundle)
    await db.commit()
    assert (await db.execute(select(BundleServer))).scalars().all() == []
    assert (await db.execute(select(BundleTool))).scalars().all() == []


async def test_bundle_server_pair_unique(db):
    server = await _mk_server(db)
    bundle = Bundle(name="b1")
    db.add(bundle)
    await db.commit()

    db.add(BundleServer(bundle_id=bundle.id, server_id=server.id))
    await db.commit()
    db.add(BundleServer(bundle_id=bundle.id, server_id=server.id))
    with pytest.raises(IntegrityError):
        await db.commit()


async def test_settings_env_prefix(monkeypatch):
    """BUNDLEMCP_ env prefix (spec 01 conventions)."""
    from bundlemcp.settings import Settings

    monkeypatch.setenv("BUNDLEMCP_REDIS_URL", "redis://elsewhere:6379/2")
    settings = Settings(_env_file=None)
    assert settings.redis_url == "redis://elsewhere:6379/2"
