"""Bootstrap tests (spec 41: BOOT-2 idempotent upserts)."""

from bundlemcp.bootstrap import BootstrapDocument, apply_document
from bundlemcp.models import Bundle, BundleServer, Endpoint, McpServer
from bundlemcp.store import session_factory
from sqlmodel import select

DOC = {
    "servers": [{"name": "echo", "url": "http://echo:9000/mcp"}],
    "bundles": [{"name": "demo", "servers": ["echo"]}],
    "endpoints": [{"name": "demo", "bundle_name": "demo", "auth_modes": ["api_key"]}],
}


async def test_apply_is_idempotent(engine, redis):
    factory = session_factory(engine)
    doc = BootstrapDocument(**DOC)

    await apply_document(factory, redis, doc)
    await apply_document(factory, redis, doc)  # BOOT-2: second run is a no-op

    async with factory() as db:
        assert len((await db.execute(select(McpServer))).scalars().all()) == 1
        assert len((await db.execute(select(Bundle))).scalars().all()) == 1
        assert len((await db.execute(select(Endpoint))).scalars().all()) == 1
        assert len((await db.execute(select(BundleServer))).scalars().all()) == 1
