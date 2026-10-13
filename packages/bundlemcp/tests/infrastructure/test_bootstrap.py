"""Bootstrap tests (MGMT-9 idempotent upserts)."""

import pytest
from bundlemcp.application.bootstrap import BootstrapDocument, BootstrapRunner
from bundlemcp.application.discovery.discovery_service import DiscoveryService
from bundlemcp.application.errors import PreconditionError
from bundlemcp.domain.endpoints.profiles import ProfileCatalog
from bundlemcp.infrastructure.crypto.token_cipher import TokenCipher
from bundlemcp.infrastructure.memory.no_upstream_connections import NoUpstreamConnections
from bundlemcp.infrastructure.memory.noop_tool_discovery import NoopToolDiscovery
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.bundle_server_row import BundleServerRow
from bundlemcp.infrastructure.postgres.rows.endpoint_row import EndpointRow
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.upstream_oauth_client_row import UpstreamOAuthClientRow
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory
from cryptography.fernet import Fernet
from sqlmodel import select


class InlineDiscovery(DiscoveryService):
    """Runs a scheduled probe to completion before returning, so a test can assert on it."""

    async def schedule_probe(self, server_id, *, announce: bool = False) -> None:
        await self.discover(server_id, announce=announce)


DOC = {
    "upstreams": [{"name": "echo", "url": "http://echo:9000/mcp"}],
    "bundles": [{"name": "demo", "upstreams": ["echo"]}],
    "endpoints": [{"name": "demo", "bundle_name": "demo", "auth_modes": ["api_key"]}],
}


OAUTH_DOC = {
    "upstreams": [
        {
            "name": "protected",
            "url": "http://protected:8001/mcp",
            "auth_mode": "upstream_oauth",
            "identity_mode": "per_user",
            "upstream_oauth": {"client_id": "bundlemcp", "client_secret": "shh"},
        }
    ],
}


async def test_upstream_oauth_client_is_applied_with_the_server(engine, redis):
    """MGMT-16: a server entry may carry the OAuth client the gateway presents upstream; it
    is stored the way the client route stores it, and re-applying changes nothing."""
    factory = session_factory(engine)
    cipher = TokenCipher([Fernet.generate_key().decode()])
    runner = BootstrapRunner(
        SqlAlchemyUnitOfWorkFactory(factory, redis),
        NoopToolDiscovery(),
        cipher=cipher,
        connections=NoUpstreamConnections(),
        profiles=ProfileCatalog.builtin(),
    )

    await runner.apply(BootstrapDocument(**OAUTH_DOC))
    await runner.apply(BootstrapDocument(**OAUTH_DOC))

    async with factory() as db:
        server = (await db.execute(select(McpServerRow))).scalar_one()
        client = (await db.execute(select(UpstreamOAuthClientRow))).scalar_one()
    assert client.server_id == server.id and client.client_id == "bundlemcp"
    assert "shh" not in (client.client_secret_encrypted or "")  # ciphertext only
    assert cipher.decrypt(client.client_secret_encrypted) == "shh"


async def test_upstream_oauth_client_needs_encryption_keys(engine, redis):
    """MGMT-16 / DEP-9: without keys the client cannot be stored, so the document does not
    apply rather than storing a secret in the clear."""
    runner = BootstrapRunner(
        SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis),
        NoopToolDiscovery(),
        cipher=None,
        connections=NoUpstreamConnections(),        profiles=ProfileCatalog.builtin(),
    )
    with pytest.raises(PreconditionError):
        await runner.apply(BootstrapDocument(**OAUTH_DOC))
    async with session_factory(engine)() as db:
        assert (await db.execute(select(McpServerRow))).first() is None  # all or nothing


async def test_apply_is_idempotent(engine, redis):
    factory = session_factory(engine)
    doc = BootstrapDocument(**DOC)
    runner = BootstrapRunner(
        SqlAlchemyUnitOfWorkFactory(factory, redis),
        NoopToolDiscovery(),
        cipher=None,
        connections=NoUpstreamConnections(),
        profiles=ProfileCatalog.builtin(),
    )

    await runner.apply(doc)
    await runner.apply(doc)  # second run is a no-op

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
    assert doc.upstreams[0].name == "echo"
    assert doc.endpoints[0].bundle_name == "demo"


async def test_fleet_seed_extends_the_demo_seed_unchanged():
    """The maintainers' seed is the demo seed plus the private fleet, so a stack
    started with either file serves the same demo bundle and endpoints."""
    import pathlib

    import yaml

    deploy = pathlib.Path(__file__).resolve().parents[4] / "deploy"
    demo = BootstrapDocument(**yaml.safe_load((deploy / "seed.yaml").read_text()))
    fleet = BootstrapDocument(**yaml.safe_load((deploy / "seed.fleet.yaml").read_text()))
    for section in ("upstreams", "bundles", "endpoints"):
        demo_entries = getattr(demo, section)
        assert getattr(fleet, section)[: len(demo_entries)] == demo_entries, section


async def test_inline_json_document_is_applied_after_the_file(engine, redis, tmp_path):
    """MGMT-8: BUNDLEMCP_BOOTSTRAP carries the document inline as JSON; both sources apply."""
    import json

    from bundlemcp.infrastructure.config.settings import EnvSettings

    seed = tmp_path / "seed.yaml"
    seed.write_text("upstreams:\n  - name: filed\n    url: http://filed/mcp\n")
    settings = EnvSettings(
        _env_file=None, bootstrap_file=str(seed), bootstrap=json.dumps(DOC), bootstrap_strict=True
    )
    factory = session_factory(engine)
    units = SqlAlchemyUnitOfWorkFactory(factory, redis)
    await BootstrapRunner(
        units,
        NoopToolDiscovery(),
        cipher=None,
        connections=NoUpstreamConnections(),
        profiles=ProfileCatalog.builtin(),
    ).run(settings)

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
    """MGMT-14/UPS-17: after a bootstrap the upstream's tools are cached with no manual refresh."""
    from bundlemcp.infrastructure.fastmcp.upstream_probe import FastMcpUpstreamProbe
    from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow

    from tests.infrastructure.test_discovery import factory_for, make_upstream

    factory = session_factory(engine)
    units = SqlAlchemyUnitOfWorkFactory(factory, redis)
    probe = FastMcpUpstreamProbe(factory_for(make_upstream(["ping"])))
    await BootstrapRunner(
        units,
        InlineDiscovery(units, probe),
        cipher=None,
        connections=NoUpstreamConnections(),
        profiles=ProfileCatalog.builtin(),
    ).apply(BootstrapDocument(**DOC))

    async with factory() as db:
        assert [t.name for t in (await db.execute(select(ToolRow))).scalars()] == ["ping"]


async def test_failing_discovery_does_not_fail_a_strict_bootstrap(engine, redis):
    """MGMT-14/MGMT-11: an unreachable upstream is recorded on the server; startup goes on."""
    import json

    from bundlemcp.domain.servers.connection_state import ConnectionState
    from bundlemcp.infrastructure.config.settings import EnvSettings
    from bundlemcp.infrastructure.fastmcp.upstream_probe import FastMcpUpstreamProbe

    from tests.infrastructure.test_discovery import failing_factory

    factory = session_factory(engine)
    units = SqlAlchemyUnitOfWorkFactory(factory, redis)
    discovery = InlineDiscovery(units, FastMcpUpstreamProbe(failing_factory))
    settings = EnvSettings(_env_file=None, bootstrap=json.dumps(DOC), bootstrap_strict=True)
    await BootstrapRunner(
        units,
        discovery,
        cipher=None,
        connections=NoUpstreamConnections(),
        profiles=ProfileCatalog.builtin(),
    ).run(settings)

    async with factory() as db:
        server = (await db.execute(select(McpServerRow))).scalar_one()
    assert server.connection_state != ConnectionState.READY


async def test_mgmt15_unknown_keys_are_rejected():
    """MGMT-15: an outdated or misspelt key fails the document instead of being ignored."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="servers"):
        BootstrapDocument.model_validate({"servers": [{"name": "a", "url": "http://a/mcp"}]})
    with pytest.raises(ValidationError, match="servers"):
        BootstrapDocument.model_validate({"bundles": [{"name": "demo", "servers": ["a"]}]})
