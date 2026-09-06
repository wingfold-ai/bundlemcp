"""Bootstrap tests (spec 41: BOOT-2 idempotent upserts)."""

from bundlemcp.bootstrap import BootstrapDocument, BootstrapRunner
from bundlemcp.models import Bundle, BundleServer, Endpoint, McpServer
from bundlemcp.services import NoopToolDiscovery
from bundlemcp.store import UnitOfWorkFactory, session_factory
from sqlmodel import select

DOC = {
    "servers": [{"name": "echo", "url": "http://echo:9000/mcp"}],
    "bundles": [{"name": "demo", "servers": ["echo"]}],
    "endpoints": [{"name": "demo", "bundle_name": "demo", "auth_modes": ["api_key"]}],
}


async def test_apply_is_idempotent(engine, redis):
    factory = session_factory(engine)
    doc = BootstrapDocument(**DOC)
    runner = BootstrapRunner(UnitOfWorkFactory(factory, redis), NoopToolDiscovery())

    await runner.apply(doc)
    await runner.apply(doc)  # BOOT-2: second run is a no-op

    async with factory() as db:
        assert len((await db.execute(select(McpServer))).scalars().all()) == 1
        assert len((await db.execute(select(Bundle))).scalars().all()) == 1
        assert len((await db.execute(select(Endpoint))).scalars().all()) == 1
        assert len((await db.execute(select(BundleServer))).scalars().all()) == 1


async def test_seed_file_parses():
    """The shipped demo seed is a valid document."""
    import pathlib

    import yaml

    root = pathlib.Path(__file__).resolve().parents[3]
    data = yaml.safe_load((root / "deploy" / "seed.yaml").read_text())
    doc = BootstrapDocument(**data)
    assert doc.servers[0].name == "echo"
    assert doc.endpoints[0].bundle_name == "demo"


async def test_inline_json_document_is_applied_after_the_file(engine, redis, tmp_path):
    """BOOT-1: BUNDLEMCP_BOOTSTRAP carries the document inline as JSON; both sources apply."""
    import json

    from bundlemcp.settings import Settings

    seed = tmp_path / "seed.yaml"
    seed.write_text("servers:\n  - name: filed\n    url: http://filed/mcp\n")
    settings = Settings(
        _env_file=None, bootstrap_file=str(seed), bootstrap=json.dumps(DOC), bootstrap_strict=True
    )
    factory = session_factory(engine)
    await BootstrapRunner(UnitOfWorkFactory(factory, redis), NoopToolDiscovery()).run(settings)

    async with factory() as db:
        names = {s.name for s in (await db.execute(select(McpServer))).scalars()}
    assert names == {"filed", "echo"}


def test_document_version_is_checked():
    """A document from a format this build does not know is refused, not misread."""
    import pytest
    from bundlemcp.bootstrap import parse_document
    from pydantic import ValidationError

    assert parse_document('{"version": 1}').version == 1
    assert parse_document("").version == 1
    with pytest.raises(ValidationError):
        parse_document('{"version": 2}')
