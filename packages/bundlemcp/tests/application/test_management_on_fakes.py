"""Use cases run on the in-memory fakes: no database, no live store, no app."""

import uuid

import pytest
from bundlemcp.application.bootstrap.bootstrap_document import BootstrapDocument
from bundlemcp.application.bootstrap.bootstrap_runner import BootstrapRunner
from bundlemcp.application.contracts.upstream.upstream_probe import ProbeResult
from bundlemcp.application.discovery.discovery_service import DiscoveryService
from bundlemcp.application.errors import ConflictError, NotFoundError
from bundlemcp.application.management.bundle_service import BundleService
from bundlemcp.application.management.endpoint_service import EndpointService
from bundlemcp.application.management.server_service import ServerService
from bundlemcp.application.schemas import (
    BundleServerUpdate,
    BundleUpsert,
    DiscoveryResult,
    EndpointUpsert,
    ServerUpsert,
)
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.endpoints.profiles import ProfileCatalog
from bundlemcp.domain.servers.connection_state import ConnectionState
from bundlemcp.domain.servers.identity_mode import IdentityMode
from bundlemcp.domain.servers.probed_tool import ProbedTool
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
    InMemoryUnitOfWorkFactory,
)
from bundlemcp.infrastructure.memory.no_upstream_connections import NoUpstreamConnections
from bundlemcp.infrastructure.memory.noop_tool_discovery import NoopToolDiscovery


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


async def test_server_upsert_is_idempotent_and_publishes_invalidation(uow):
    """UPS-1/SES-17: the second upsert updates in place and each commit announces the change."""
    servers = ServerService(uow, discovery=NoopToolDiscovery(), public_base="http://gw")
    first = await servers.upsert(ServerUpsert(name="echo", url="http://echo/mcp"))
    second = await servers.upsert(
        ServerUpsert(name="echo", url="http://echo/mcp", description="renamed")
    )
    assert first.id == second.id
    assert second.description == "renamed"
    assert [e.action for e in uow.published] == ["created", "updated"]
    assert [e.entity_type for e in uow.published] == ["server", "server"]


async def test_rename_of_a_bundle_member_needs_force(uow):
    """UPS-5: renaming a member changes client-visible tool names, so it must be acknowledged."""
    servers = ServerService(uow, discovery=NoopToolDiscovery(), public_base="http://gw")
    bundles = BundleService(uow, public_base="http://gw")
    await servers.upsert(ServerUpsert(name="echo", url="http://echo/mcp"))
    await bundles.upsert(BundleUpsert(name="demo"))
    await bundles.set_member("demo", "echo", BundleServerUpdate())
    with pytest.raises(ConflictError):
        await servers.rename("echo", "echo2", force=False)
    renamed = await servers.rename("echo", "echo2", force=True)
    assert renamed.name == "echo2"


async def test_anonymous_endpoint_cannot_expose_a_per_user_upstream(uow):
    """UPS-30 at the endpoint edge, checked through the ports alone."""
    servers = ServerService(uow, discovery=NoopToolDiscovery(), public_base="http://gw")
    bundles = BundleService(uow, public_base="http://gw")
    endpoints = EndpointService(uow, profiles=ProfileCatalog.builtin())
    await servers.upsert(
        ServerUpsert(
            name="gh",
            url="http://gh/mcp",
            auth_mode=ServerAuthMode.UPSTREAM_OAUTH,
            identity_mode=IdentityMode.PER_USER,
        )
    )
    await bundles.upsert(BundleUpsert(name="demo"))
    await bundles.set_member("demo", "gh", BundleServerUpdate())
    with pytest.raises(ConflictError):
        await endpoints.upsert(
            EndpointUpsert(
                name="open",
                bundle_name="demo",
                auth_modes=[EndpointAuthMode.NONE],
                allow_unauthenticated=True,
            )
        )
    keyed = await endpoints.upsert(
        EndpointUpsert(name="keyed", bundle_name="demo", auth_modes=[EndpointAuthMode.API_KEY])
    )
    assert keyed.name == "keyed"


async def test_endpoint_for_unknown_bundle_is_not_found(uow):
    with pytest.raises(NotFoundError):
        await EndpointService(uow, profiles=ProfileCatalog.builtin()).upsert(
            EndpointUpsert(name="ep", bundle_name="missing")
        )


class CommitAwareDiscovery:
    """Records each probe request with how many commits the unit of work had seen by then."""

    def __init__(self, uow: InMemoryUnitOfWork) -> None:
        self._uow = uow
        self.probes: list[tuple[str, int]] = []

    async def schedule_probe(self, server_id) -> None:
        server = await self._uow.servers.get(server_id)
        self.probes.append((server.name, self._uow.committed))

    async def discover(self, server_id) -> DiscoveryResult:
        return DiscoveryResult(error="not used here")


async def test_bootstrap_discovers_its_servers_after_the_commit(uow):
    """MGMT-14/UPS-17: every bootstrapped server is probed, and only once it is committed."""
    document = BootstrapDocument.model_validate(
        {
            "upstreams": [
                {"name": "echo", "url": "http://echo/mcp"},
                {"name": "weather", "url": "http://weather/mcp"},
            ]
        }
    )
    discovery = CommitAwareDiscovery(uow)
    await BootstrapRunner(
        InMemoryUnitOfWorkFactory(uow),
        discovery,
        cipher=None,
        connections=NoUpstreamConnections(),
        profiles=ProfileCatalog.builtin(),
        public_base="http://gw",
    ).apply(document)
    assert discovery.probes == [("echo", 1), ("weather", 1)]


async def test_failed_bootstrap_probes_nothing(uow):
    """MGMT-14: a document that does not land schedules no discovery."""
    document = BootstrapDocument.model_validate(
        {
            "upstreams": [{"name": "echo", "url": "http://echo/mcp"}],
            "endpoints": [{"name": "ep", "bundle_name": "missing"}],
        }
    )
    discovery = CommitAwareDiscovery(uow)
    with pytest.raises(NotFoundError):
        await BootstrapRunner(
            InMemoryUnitOfWorkFactory(uow),
            discovery,
            cipher=None,
            connections=NoUpstreamConnections(),
            profiles=ProfileCatalog.builtin(),
            public_base="http://gw",
        ).apply(document)
    assert discovery.probes == []


async def _mark_reachable(uow: InMemoryUnitOfWork, name: str) -> None:
    """Record a successful probe, as discovery would after reaching the upstream."""
    server = await uow.servers.by_name(name)
    server.connection_state = ConnectionState.READY
    uow.servers.add(server)


async def test_unchanged_upsert_of_a_working_server_does_not_probe(uow):
    """UPS-2: re-applying the same config to a reachable server stays off the upstream."""
    discovery = CommitAwareDiscovery(uow)
    servers = ServerService(uow, discovery=discovery, public_base="http://gw")
    body = ServerUpsert(name="echo", url="http://echo/mcp", forward_headers={"x-a": "x-a"})
    await servers.upsert(body)
    await _mark_reachable(uow, "echo")
    await servers.upsert(body)
    await servers.upsert(body.model_copy(update={"description": "only a label changed"}))
    assert [name for name, _ in discovery.probes] == ["echo"]


@pytest.mark.parametrize(
    "change",
    [
        {"url": "http://echo-2/mcp"},
        {"static_headers": {"Authorization": "Bearer new"}},
        {"forward_headers": {"x-b": "x-b"}},
        {"protocol_mode": "legacy"},
        {"send_identity_header": False},
        {"identity_mode": IdentityMode.PER_USER},
    ],
)
async def test_upsert_that_changes_discovery_inputs_probes(uow, change):
    """UPS-2: a change to how the upstream is reached is probed again."""
    discovery = CommitAwareDiscovery(uow)
    servers = ServerService(uow, discovery=discovery, public_base="http://gw")
    body = ServerUpsert(name="echo", url="http://echo/mcp")
    await servers.upsert(body)
    await _mark_reachable(uow, "echo")
    await servers.upsert(body.model_copy(update=change))
    assert [name for name, _ in discovery.probes] == ["echo", "echo"]


async def test_unchanged_upsert_retries_a_server_whose_last_probe_failed(uow):
    """UPS-2: re-applying a config still retries a server that was never reached."""
    discovery = CommitAwareDiscovery(uow)
    servers = ServerService(uow, discovery=discovery, public_base="http://gw")
    body = ServerUpsert(name="echo", url="http://echo/mcp")
    await servers.upsert(body)
    await servers.upsert(body)
    assert [name for name, _ in discovery.probes] == ["echo", "echo"]


async def test_reapplied_bootstrap_does_not_probe_working_servers(uow):
    """MGMT-14/UPS-2: a gateway restart that re-applies the same document wakes no upstream."""
    document = BootstrapDocument.model_validate(
        {"upstreams": [{"name": "echo", "url": "http://echo/mcp"}]}
    )
    discovery = CommitAwareDiscovery(uow)
    runner = BootstrapRunner(
        InMemoryUnitOfWorkFactory(uow),
        discovery,
        cipher=None,
        connections=NoUpstreamConnections(),
        profiles=ProfileCatalog.builtin(),
        public_base="http://gw",
    )
    await runner.apply(document)
    await _mark_reachable(uow, "echo")
    await runner.apply(document)
    assert [name for name, _ in discovery.probes] == ["echo"]


async def test_bootstrap_document_lands_in_one_commit(uow):
    """MGMT-9: the whole document is applied inside one atomic scope."""
    document = BootstrapDocument.model_validate(
        {
            "upstreams": [{"name": "echo", "url": "http://echo/mcp"}],
            "bundles": [{"name": "demo", "upstreams": ["echo"]}],
            "endpoints": [{"name": "ep", "bundle_name": "demo"}],
        }
    )
    await BootstrapRunner(
        InMemoryUnitOfWorkFactory(uow),
        NoopToolDiscovery(),
        cipher=None,
        connections=NoUpstreamConnections(),
        profiles=ProfileCatalog.builtin(),
        public_base="http://gw",
    ).apply(document)
    assert uow.committed == 1
    assert await uow.endpoints.by_name("ep") is not None
    assert len(await uow.memberships.for_bundle((await uow.bundles.by_name("demo")).id)) == 1


class ScriptedProbe:
    """An upstream probe that lists whichever tools the test sets."""

    def __init__(self, *names: str) -> None:
        self.names = list(names)

    async def probe(self, server, headers) -> ProbeResult:
        return ProbeResult(
            tools=[ProbedTool(name=n) for n in self.names], capabilities=None, protocol_version=None
        )


async def _discovered_member(uow) -> tuple[DiscoveryService, ScriptedProbe, uuid.UUID]:
    """Server echo, probed once with tools alpha and beta, as a member of bundle demo."""
    await ServerService(uow, discovery=NoopToolDiscovery(), public_base="http://gw").upsert(
        ServerUpsert(name="echo", url="http://echo/mcp")
    )
    bundles = BundleService(uow, public_base="http://gw")
    await bundles.upsert(BundleUpsert(name="demo"))
    await bundles.set_member("demo", "echo", BundleServerUpdate())
    probe = ScriptedProbe("alpha", "beta")
    discovery = DiscoveryService(InMemoryUnitOfWorkFactory(uow), probe)
    server = await uow.servers.by_name("echo")
    await discovery.discover(server.id)
    return discovery, probe, server.id


async def test_ups18_unchanged_run_invalidates_nothing(uow):
    """UPS-18: a discovery that finds nothing new announces nothing to the bundles."""
    discovery, _probe, server_id = await _discovered_member(uow)
    uow.published.clear()

    result = await discovery.discover(server_id)

    assert result.changed == 0
    assert [e for e in uow.published if e.entity_type == "bundle"] == []


async def test_ups19_vanished_tool_invalidates_the_bundle(uow):
    """UPS-18/UPS-19: a tool going stale is a change of the tool set, so bundles re-list."""
    discovery, probe, server_id = await _discovered_member(uow)
    uow.published.clear()
    probe.names = ["alpha"]

    result = await discovery.discover(server_id)

    assert result.changed == 1
    assert [e.key for e in uow.published if e.entity_type == "bundle"] == ["demo"]


async def test_bnd17_catalogue_leaves_out_stale_tools(uow):
    """BND-17/UPS-19: the catalogue shows what is served, so a stale tool is not in it."""
    discovery, probe, server_id = await _discovered_member(uow)
    probe.names = ["alpha"]
    await discovery.discover(server_id)

    bundle = await uow.bundles.by_name("demo")
    catalogue = await BundleService(uow, public_base="http://gw").catalogue_tools(bundle.id)

    assert [tool.name for tool in catalogue] == ["echo__alpha"]


async def test_bnd1_bootstrap_sets_order(uow):
    """BND-1: a bootstrap document's member list sets the order of the members it names; a
    member it does not name follows them."""
    servers = ServerService(uow, discovery=NoopToolDiscovery(), public_base="http://gw")
    for name in ("alpha", "extra", "zeta"):
        await servers.upsert(ServerUpsert(name=name, url=f"http://{name}/mcp"))
    bundles = BundleService(uow, public_base="http://gw")
    await bundles.upsert(BundleUpsert(name="demo"))
    await bundles.set_member("demo", "extra", BundleServerUpdate())

    document = BootstrapDocument.model_validate(
        {"bundles": [{"name": "demo", "upstreams": ["zeta", "alpha"]}]}
    )
    await BootstrapRunner(
        InMemoryUnitOfWorkFactory(uow),
        NoopToolDiscovery(),
        cipher=None,
        connections=NoUpstreamConnections(),
        profiles=ProfileCatalog.builtin(),
        public_base="http://gw",
    ).apply(document)

    members = await BundleService(uow, public_base="http://gw").list_members("demo")
    assert [m.server_name for m in members] == ["zeta", "alpha", "extra"]


GATEWAY = "https://gw.example.com"


@pytest.mark.parametrize(
    "url",
    ["https://gw.example.com/loop-ep/mcp", "https://GW.Example.com:443/later/mcp/"],
    ids=["own-endpoint", "spelling-variant-of-an-endpoint-not-created-yet"],
)
async def test_bnd5_own_endpoint_is_refused_as_a_member(uow, url):
    """BND-5: adding the gateway itself to a bundle is a conflict, and nothing is stored."""
    servers = ServerService(uow, discovery=NoopToolDiscovery(), public_base=GATEWAY)
    bundles = BundleService(uow, public_base=GATEWAY)
    await servers.upsert(ServerUpsert(name="loop", url=url))  # a non-member may point anywhere
    await bundles.upsert(BundleUpsert(name="b1"))
    with pytest.raises(ConflictError, match="BND-5"):
        await bundles.set_member("b1", "loop", BundleServerUpdate())
    assert await bundles.list_members("b1") == []


async def test_bnd5_other_paths_and_hosts_are_members_like_any_other(uow):
    servers = ServerService(uow, discovery=NoopToolDiscovery(), public_base=GATEWAY)
    bundles = BundleService(uow, public_base=GATEWAY)
    await bundles.upsert(BundleUpsert(name="b1"))
    for name, url in (
        ("weather", "https://gw.example.com/tools/weather/mcp"),
        ("api", "https://api.example.com/loop-ep/mcp"),
    ):
        await servers.upsert(ServerUpsert(name=name, url=url))
        await bundles.set_member("b1", name, BundleServerUpdate())
    assert len(await bundles.list_members("b1")) == 2


async def test_bnd5_a_members_url_cannot_be_changed_to_the_gateway(uow):
    """BND-5: the URL change is refused and the stored URL stays as it was."""
    servers = ServerService(uow, discovery=NoopToolDiscovery(), public_base=GATEWAY)
    bundles = BundleService(uow, public_base=GATEWAY)
    await servers.upsert(ServerUpsert(name="weather", url="http://weather/mcp"))
    await bundles.upsert(BundleUpsert(name="b1"))
    await bundles.set_member("b1", "weather", BundleServerUpdate())
    with pytest.raises(ConflictError, match="BND-5"):
        await servers.upsert(ServerUpsert(name="weather", url=f"{GATEWAY}/b1-ep/mcp"))
    assert (await servers.get("weather")).url == "http://weather/mcp"
