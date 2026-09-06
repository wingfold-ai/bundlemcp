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
    monkeypatch.setenv("BUNDLEMCP_ADMIN_EMAILS", '["a@example.com"]')
    settings = Settings(_env_file=None)
    assert settings.redis_url == "redis://elsewhere:6379/2"
    assert settings.admin_emails == ["a@example.com"]


def test_scoped_service_key_reaches_only_its_endpoints():
    """KEY-2: the endpoint scope applies whatever the key's kind."""
    import uuid

    from bundlemcp.models import ApiKey, ApiKeyKind

    inside, outside = uuid.uuid4(), uuid.uuid4()
    for kind in (ApiKeyKind.ENDPOINT, ApiKeyKind.SERVICE):
        scoped = ApiKey(
            name="k", key_hash="h", key_prefix="p", kind=kind, endpoint_ids=[str(inside)]
        )
        assert scoped.reaches(inside) and not scoped.reaches(outside)
        unscoped = ApiKey(name="k", key_hash="h", key_prefix="p", kind=kind)
        assert unscoped.reaches(outside)


def test_service_error_status_is_inherited():
    """A subclass of a domain error keeps its parent's HTTP status."""
    from bundlemcp.services.errors import ConflictError, OAuthError, ServiceError

    class NameCollisionError(ConflictError):
        pass

    assert NameCollisionError("x").status == 409
    assert ServiceError("x").status == 500
    assert OAuthError("invalid_grant").status == 400
    assert OAuthError("invalid_client", status=401).status == 401


def test_config_values_are_validated_strictly():
    """A stored config value must already have the key's type; nothing is converted."""
    from bundlemcp.services.config_service import UnknownConfigKey, coerce

    assert coerce("call_timeout", 30) == 30.0
    assert coerce("reset_timeout_on_progress", False) is False
    assert coerce("session_lifetime", 10) == 10
    for key, value in [
        ("call_timeout", "30"),
        ("reset_timeout_on_progress", 1),
        ("session_lifetime", True),
        ("session_lifetime", 1.5),
    ]:
        with pytest.raises(ValueError, match=key):
            coerce(key, value)
    with pytest.raises(UnknownConfigKey):
        coerce("nope", 1)
