"""Bootstrap tests (MGMT-9 idempotent upserts)."""

import pytest
from bundlemcp.application.bootstrap import BootstrapDocument, BootstrapRunner
from bundlemcp.application.discovery.discovery_service import DiscoveryService
from bundlemcp.application.discovery.upstream_health import UpstreamHealth
from bundlemcp.application.errors import PreconditionError
from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.domain.endpoints.profiles import ProfileCatalog
from bundlemcp.domain.servers.protocol_mode import NegotiationMode
from bundlemcp.domain.shared.sha256_secret_hasher import Sha256SecretHasher
from bundlemcp.domain.shared.system_clock import SystemClock
from bundlemcp.infrastructure.crypto.token_cipher import TokenCipher
from bundlemcp.infrastructure.memory.no_upstream_connections import NoUpstreamConnections
from bundlemcp.infrastructure.memory.noop_tool_discovery import NoopToolDiscovery
from bundlemcp.infrastructure.memory.sequential_secret_generator import SequentialSecretGenerator
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.bundle_server_row import BundleServerRow
from bundlemcp.infrastructure.postgres.rows.endpoint_row import EndpointRow
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.upstream_oauth_client_row import UpstreamOAuthClientRow
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory
from bundlemcp.infrastructure.valkey.failure_streak_store import ValkeyFailureStreak
from cryptography.fernet import Fernet
from sqlmodel import select


def _health(units, redis) -> UpstreamHealth:
    return UpstreamHealth(units, ValkeyFailureStreak(redis), RuntimeConfig(units))


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
        public_base="http://gw",
        hasher=Sha256SecretHasher(),
        generator=SequentialSecretGenerator(),
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
        connections=NoUpstreamConnections(),
        profiles=ProfileCatalog.builtin(),
        public_base="http://gw",
        hasher=Sha256SecretHasher(),
        generator=SequentialSecretGenerator(),
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
        public_base="http://gw",
        hasher=Sha256SecretHasher(),
        generator=SequentialSecretGenerator(),
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


async def test_demo_seed_keeps_the_identity_demo_apart():
    """DOC-3: the demo seed registers the identity demo in a bundle and endpoint of its own,
    so the demo bundle keeps the quickstart's servers; the forwarded authorization replaces
    the static discovery header because both use the same name."""
    import pathlib

    import yaml

    deploy = pathlib.Path(__file__).resolve().parents[4] / "deploy"
    doc = BootstrapDocument(**yaml.safe_load((deploy / "seed.yaml").read_text()))
    bundles = {bundle.name: bundle.upstreams for bundle in doc.bundles}
    assert bundles["demo"] == ["echo", "oauth-demo"]
    assert [name for name, members in bundles.items() if "identity-demo" in members] == ["identity"]
    assert {endpoint.name: endpoint.bundle_name for endpoint in doc.endpoints}["identity"] == (
        "identity"
    )
    [demo] = [server for server in doc.upstreams if server.name == "identity-demo"]
    assert demo.forward_headers["authorization"] == "authorization"
    assert "authorization" in demo.static_headers


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
        public_base="http://gw",
        hasher=Sha256SecretHasher(),
        generator=SequentialSecretGenerator(),
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
        InlineDiscovery(units, probe, health=_health(units, redis), clock=SystemClock()),
        cipher=None,
        connections=NoUpstreamConnections(),
        profiles=ProfileCatalog.builtin(),
        public_base="http://gw",
        hasher=Sha256SecretHasher(),
        generator=SequentialSecretGenerator(),
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
    discovery = InlineDiscovery(
        units,
        FastMcpUpstreamProbe(failing_factory),
        health=_health(units, redis),
        clock=SystemClock(),
    )
    settings = EnvSettings(_env_file=None, bootstrap=json.dumps(DOC), bootstrap_strict=True)
    await BootstrapRunner(
        units,
        discovery,
        cipher=None,
        connections=NoUpstreamConnections(),
        profiles=ProfileCatalog.builtin(),
        public_base="http://gw",
        hasher=Sha256SecretHasher(),
        generator=SequentialSecretGenerator(),
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


def test_ep23_former_profile_identifier_fails_the_document():
    """EP-23: a bootstrap endpoint naming a former profile fails on its profile field."""
    from pydantic import ValidationError

    document = {"endpoints": [{"name": "c", "bundle_name": "demo", "profile": "claude"}]}
    with pytest.raises(ValidationError, match=r"endpoints\.0\.profile") as raised:
        BootstrapDocument.model_validate(document)
    assert "oauth_only" in str(raised.value)


def test_ep24_a_bootstrap_endpoint_accepts_allowed_origins():
    """EP-24: a bootstrap document may list an endpoint's allowed browser origins."""
    document = BootstrapDocument.model_validate(
        {
            "endpoints": [
                {
                    "name": "web",
                    "bundle_name": "demo",
                    "auth_modes": ["none"],
                    "allow_unauthenticated": True,
                    "allowed_origins": ["https://App.example"],
                }
            ]
        }
    )
    assert document.endpoints[0].allowed_origins == ["https://app.example"]


async def test_bnd5_a_bootstrap_document_cannot_make_the_gateway_a_member(engine, redis):
    """BND-5: a document listing one of the gateway's own endpoints as a member fails whole."""
    from bundlemcp.application.errors import ConflictError

    document = BootstrapDocument(
        upstreams=[{"name": "loop", "url": "http://gw/loop-ep/mcp"}],
        bundles=[{"name": "demo", "upstreams": ["loop"]}],
    )
    runner = BootstrapRunner(
        SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis),
        NoopToolDiscovery(),
        cipher=None,
        connections=NoUpstreamConnections(),
        profiles=ProfileCatalog.builtin(),
        public_base="http://gw",
        hasher=Sha256SecretHasher(),
        generator=SequentialSecretGenerator(),
    )
    with pytest.raises(ConflictError, match="BND-5"):
        await runner.apply(document)
    async with session_factory(engine)() as db:
        assert (await db.execute(select(BundleServerRow))).first() is None


async def test_mgmt10_an_unknown_scope_lands_nothing_of_the_document(engine, redis):
    """MGMT-10: a key scoped to an undefined endpoint rolls the whole document back."""
    doc = BootstrapDocument.model_validate(
        {
            **DOC,
            "api_keys": [{"name": "ci", "endpoints": ["nowhere"], "value_from_env": "CI_KEY"}],
        }
    )
    runner = BootstrapRunner(
        SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis),
        NoopToolDiscovery(),
        cipher=None,
        connections=NoUpstreamConnections(),
        profiles=ProfileCatalog.builtin(),
        public_base="http://gw",
        hasher=Sha256SecretHasher(),
        generator=SequentialSecretGenerator(),
        environ={"CI_KEY": "bmcp_sk_" + "c" * 43},
    )
    with pytest.raises(ValueError, match="nowhere"):
        await runner.apply(doc)
    async with session_factory(engine)() as db:
        assert (await db.execute(select(EndpointRow))).scalars().all() == []
        assert (await db.execute(select(McpServerRow))).scalars().all() == []


async def test_ups10_bootstrap_document_may_use_the_legacy_alias(engine, redis):
    """UPS-10: a bootstrap document naming the handshake-only mode 'legacy' creates the upstream
    in 'session' mode."""
    units = SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis)
    runner = BootstrapRunner(
        units,
        NoopToolDiscovery(),
        cipher=None,
        connections=NoUpstreamConnections(),
        profiles=ProfileCatalog.builtin(),
        public_base="http://gw",
        hasher=Sha256SecretHasher(),
        generator=SequentialSecretGenerator(),
    )
    doc = {"upstreams": [{"name": "old", "url": "http://old/mcp", "protocol_mode": "legacy"}]}
    await runner.apply(BootstrapDocument(**doc))
    async with units.open() as uow:
        server = await uow.servers.by_name("old")
    assert server is not None
    assert server.protocol_mode == NegotiationMode.SESSION
