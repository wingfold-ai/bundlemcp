"""Bootstrap tests (spec 41: BOOT-2 idempotent upserts)."""

from bundlemcp.application.bootstrap import BootstrapDocument, BootstrapRunner
from bundlemcp.application.discovery.discovery_service import DiscoveryService
from bundlemcp.infrastructure.memory.noop_tool_discovery import NoopToolDiscovery
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.bundle_server_row import BundleServerRow
from bundlemcp.infrastructure.postgres.rows.endpoint_row import EndpointRow
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory
from sqlmodel import select


class InlineDiscovery(DiscoveryService):
    """Runs a scheduled probe to completion before returning, so a test can assert on it."""

    async def schedule_probe(self, server_id, *, announce: bool = False) -> None:
        await self.discover(server_id, announce=announce)


DOC = {
    "servers": [{"name": "echo", "url": "http://echo:9000/mcp"}],
    "bundles": [{"name": "demo", "servers": ["echo"]}],
    "endpoints": [{"name": "demo", "bundle_name": "demo", "auth_modes": ["api_key"]}],
}


async def test_apply_is_idempotent(engine, redis):
    factory = session_factory(engine)
    doc = BootstrapDocument(**DOC)
    runner = BootstrapRunner(SqlAlchemyUnitOfWorkFactory(factory, redis), NoopToolDiscovery())

    await runner.apply(doc)
    await runner.apply(doc)  # BOOT-2: second run is a no-op

    async with factory() as db:
        assert len((await db.execute(select(McpServerRow))).scalars().all()) == 1
        assert len((await db.execute(select(BundleRow))).scalars().all()) == 1
        assert len((await db.execute(select(EndpointRow))).scalars().all()) == 1
        assert len((await db.execute(select(BundleServerRow))).scalars().all()) == 1


async def test_seed_file_parses():
    """The shipped demo seed is a valid document."""
    import pathlib

    import yaml

    root = pathlib.Path(__file__).resolve().parents[4]
    data = yaml.safe_load((root / "deploy" / "seed.yaml").read_text())
    doc = BootstrapDocument(**data)
    assert doc.servers[0].name == "echo"
    assert doc.endpoints[0].bundle_name == "demo"


async def test_inline_json_document_is_applied_after_the_file(engine, redis, tmp_path):
    """BOOT-1: BUNDLEMCP_BOOTSTRAP carries the document inline as JSON; both sources apply."""
    import json

    from bundlemcp.infrastructure.config.settings import EnvSettings

    seed = tmp_path / "seed.yaml"
    seed.write_text("servers:\n  - name: filed\n    url: http://filed/mcp\n")
    settings = EnvSettings(
        _env_file=None, bootstrap_file=str(seed), bootstrap=json.dumps(DOC), bootstrap_strict=True
    )
    factory = session_factory(engine)
    units = SqlAlchemyUnitOfWorkFactory(factory, redis)
    await BootstrapRunner(units, NoopToolDiscovery()).run(settings)

    async with factory() as db:
        names = {s.name for s in (await db.execute(select(McpServerRow))).scalars()}
    assert names == {"filed", "echo"}


def test_document_version_is_checked():
    """A document from a format this build does not know is refused, not misread."""
    import pytest
    from bundlemcp.application.bootstrap import parse_document
    from pydantic import ValidationError

    assert parse_document('{"version": 1}').version == 1
    assert parse_document("").version == 1
    with pytest.raises(ValidationError):
        parse_document('{"version": 2}')


async def test_fresh_bootstrap_serves_discovered_tools(engine, redis):
    """BOOT-7/DISC-1: after a bootstrap the upstream's tools are cached without a manual refresh."""
    from bundlemcp.infrastructure.fastmcp.upstream_probe import FastMcpUpstreamProbe
    from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow

    from tests.infrastructure.test_discovery import factory_for, make_upstream

    factory = session_factory(engine)
    units = SqlAlchemyUnitOfWorkFactory(factory, redis)
    probe = FastMcpUpstreamProbe(factory_for(make_upstream(["ping"])))
    await BootstrapRunner(units, InlineDiscovery(units, probe)).apply(BootstrapDocument(**DOC))

    async with factory() as db:
        assert [t.name for t in (await db.execute(select(ToolRow))).scalars()] == ["ping"]


async def test_failing_discovery_does_not_fail_a_strict_bootstrap(engine, redis):
    """BOOT-7/BOOT-4: an unreachable upstream is recorded on the server; startup goes on."""
    import json

    from bundlemcp.domain.servers.connection_state import ConnectionState
    from bundlemcp.infrastructure.config.settings import EnvSettings
    from bundlemcp.infrastructure.fastmcp.upstream_probe import FastMcpUpstreamProbe

    from tests.infrastructure.test_discovery import failing_factory

    factory = session_factory(engine)
    units = SqlAlchemyUnitOfWorkFactory(factory, redis)
    discovery = InlineDiscovery(units, FastMcpUpstreamProbe(failing_factory))
    settings = EnvSettings(_env_file=None, bootstrap=json.dumps(DOC), bootstrap_strict=True)
    await BootstrapRunner(units, discovery).run(settings)

    async with factory() as db:
        server = (await db.execute(select(McpServerRow))).scalar_one()
    assert server.connection_state != ConnectionState.READY
