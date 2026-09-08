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
    EndpointUpsert,
    ServerUpsert,
)
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.servers.identity_mode import IdentityMode
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
    InMemoryUnitOfWorkFactory,
)
from bundlemcp.infrastructure.memory.noop_tool_discovery import NoopToolDiscovery


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


async def test_server_upsert_is_idempotent_and_publishes_invalidation(uow):
    """SRV-1/STP-1: the second upsert updates in place and each commit announces the change."""
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
    """SRV-5: renaming a member changes client-visible tool names, so it must be acknowledged."""
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
    """UPO-6 at the endpoint edge, checked through the ports alone."""
    servers = ServerService(uow, discovery=NoopToolDiscovery())
    bundles = BundleService(uow)
    endpoints = EndpointService(uow)
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
        await EndpointService(uow).upsert(EndpointUpsert(name="ep", bundle_name="missing"))


async def test_bootstrap_document_lands_in_one_commit(uow):
    """BOOT-2: the whole document is applied inside one atomic scope."""
    document = BootstrapDocument.model_validate(
        {
            "servers": [{"name": "echo", "url": "http://echo/mcp"}],
            "bundles": [{"name": "demo", "servers": ["echo"]}],
            "endpoints": [{"name": "ep", "bundle_name": "demo"}],
        }
    )
    await BootstrapRunner(InMemoryUnitOfWorkFactory(uow), NoopToolDiscovery()).apply(document)
    assert uow.committed == 1
    assert await uow.endpoints.by_name("ep") is not None
    assert len(await uow.memberships.for_bundle((await uow.bundles.by_name("demo")).id)) == 1
