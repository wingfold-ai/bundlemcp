"""Use cases run on the in-memory fakes: no database, no live store, no app."""

import pytest
from bundlemcp.application.bootstrap.bootstrap_document import BootstrapDocument
from bundlemcp.application.bootstrap.bootstrap_runner import BootstrapRunner
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
    servers = ServerService(uow, discovery=NoopToolDiscovery())
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
    servers = ServerService(uow, discovery=NoopToolDiscovery())
    bundles = BundleService(uow)
    await servers.upsert(ServerUpsert(name="echo", url="http://echo/mcp"))
    await bundles.upsert(BundleUpsert(name="demo"))
    await bundles.set_member("demo", "echo", BundleServerUpdate())
    with pytest.raises(ConflictError):
        await servers.rename("echo", "echo2", force=False)
    renamed = await servers.rename("echo", "echo2", force=True)
    assert renamed.name == "echo2"


async def test_anonymous_endpoint_cannot_expose_a_per_user_upstream(uow):
    """UPS-30 at the endpoint edge, checked through the ports alone."""
    servers = ServerService(uow, discovery=NoopToolDiscovery())
    bundles = BundleService(uow)
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
    servers = ServerService(uow, discovery=discovery)
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
    servers = ServerService(uow, discovery=discovery)
    body = ServerUpsert(name="echo", url="http://echo/mcp")
    await servers.upsert(body)
    await _mark_reachable(uow, "echo")
    await servers.upsert(body.model_copy(update=change))
    assert [name for name, _ in discovery.probes] == ["echo", "echo"]


async def test_unchanged_upsert_retries_a_server_whose_last_probe_failed(uow):
    """UPS-2: re-applying a config still retries a server that was never reached."""
    discovery = CommitAwareDiscovery(uow)
    servers = ServerService(uow, discovery=discovery)
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
    ).apply(document)
    assert uow.committed == 1
    assert await uow.endpoints.by_name("ep") is not None
    assert len(await uow.memberships.for_bundle((await uow.bundles.by_name("demo")).id)) == 1
