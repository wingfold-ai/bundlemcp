"""Credentials stay with the URL they were obtained for (UPS-41, UPS-42) on the in-memory fakes."""

import uuid

import pytest
from bundlemcp.application.errors import ConflictError
from bundlemcp.application.management.audit_filter import AuditFilter
from bundlemcp.application.management.server_service import ServerService
from bundlemcp.application.schemas import ServerUpsert
from bundlemcp.application.upstream_oauth.account_connect_prompts import AccountConnectPrompts
from bundlemcp.application.upstream_oauth.upstream_credential_resolver import (
    UpstreamCredentialResolver,
)
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.access.principal import Principal
from bundlemcp.domain.access.principal_kind import PrincipalKind
from bundlemcp.domain.access.user import User
from bundlemcp.domain.audit.audit_kind import AuditKind
from bundlemcp.domain.upstream_oauth.client_identification import ClientIdentification
from bundlemcp.domain.upstream_oauth.upstream_client_metadata import UpstreamClientMetadata
from bundlemcp.domain.upstream_oauth.upstream_grant import UpstreamGrant
from bundlemcp.domain.upstream_oauth.upstream_metadata import UpstreamMetadata
from bundlemcp.domain.upstream_oauth.upstream_oauth_client import UpstreamOAuthClient
from bundlemcp.domain.upstream_oauth.upstream_tokens import UpstreamTokens
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import InMemoryUnitOfWork
from bundlemcp.infrastructure.memory.noop_tool_discovery import NoopToolDiscovery

from tests.application.test_upstream_oauth_on_fakes import (
    PUBLIC_BASE,
    RecordingProbe,
    discovery,
    seed_member,
    token_service,
    view_of,
)

OLD_URL = "https://seo.example/mcp"
NEW_URL = "https://other.example/mcp"
ADMIN = Principal(kind=PrincipalKind.ADMIN, user_id=str(uuid.uuid4()))
ENDPOINTS = UpstreamMetadata(authorization_endpoint="https://idp/a", token_endpoint="https://idp/t")


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


def servers(uow) -> ServerService:
    return ServerService(uow, discovery=NoopToolDiscovery(), public_base=PUBLIC_BASE)


def write(url: str, **fields) -> ServerUpsert:
    return ServerUpsert(
        name="seo", url=url, auth_mode="upstream_oauth", identity_mode="per_user", **fields
    )


async def connect_users(uow, server) -> list[User]:
    tokens = token_service(uow)
    users = [User(oidc_issuer="i", oidc_sub=sub, email=f"{sub}@x") for sub in ("a", "b")]
    for user in users:
        uow.users.add(user)
        await tokens.save(server.id, user.id, UpstreamTokens(access_token=f"t-{user.oidc_sub}"))
    await tokens.save(server.id, None, UpstreamTokens(access_token="shared"))
    return users


async def management_records(uow):
    page = await uow.audit_records.page(AuditFilter(kind=AuditKind.MANAGEMENT), offset=0, limit=10)
    return page.items


def store_client(uow, server, identification: ClientIdentification, secret=None):
    client = UpstreamOAuthClient(
        server_id=server.id,
        client_id="cid",
        client_secret_encrypted=secret,
        metadata_=UpstreamClientMetadata.obtained(ENDPOINTS, identification).with_step_up(["x"]),
    )
    uow.upstream_clients.add(client)
    return client


async def test_ups41_moving_the_url_disconnects_every_account(uow):
    """UPS-41: shared and per-user tokens are gone, and the connect tool is offered again."""
    server, bundle = seed_member(uow)
    users = await connect_users(uow, server)

    await servers(uow).upsert(write(NEW_URL), actor=ADMIN)

    assert await uow.upstream_tokens.for_server(server.id) == []
    prompts = AccountConnectPrompts(UpstreamCredentialResolver(token_service(uow), PUBLIC_BASE))
    caller = CallerIdentity.oauth_user(users[0])
    pending = await prompts.pending(view_of(server, bundle), caller)
    assert [tool.presented_name for tool in pending] == ["seo__connect_account"]


async def test_ups41_no_old_token_reaches_the_new_url(uow):
    """UPS-41: discovery of the moved server finds no connection and sends nothing."""
    server, _ = seed_member(uow)
    await connect_users(uow, server)

    await servers(uow).upsert(write(NEW_URL), actor=ADMIN)

    probe = RecordingProbe()
    result = await discovery(uow, token_service(uow), probe).discover(server.id)
    assert result.error == "upstream not connected"
    assert probe.headers == []


@pytest.mark.parametrize(
    "identification",
    [
        ClientIdentification.DYNAMIC_REGISTRATION,
        ClientIdentification.METADATA_DOCUMENT,
        ClientIdentification.PREREGISTERED_REQUIRED,
    ],
)
async def test_ups41_a_client_the_gateway_obtained_is_dropped(uow, identification):
    """UPS-41: the next connect discovers and registers at the new resource."""
    server, _ = seed_member(uow)
    store_client(uow, server, identification)

    await servers(uow).upsert(write(NEW_URL), actor=ADMIN)

    assert await uow.upstream_clients.for_server(server.id) is None


async def test_ups41_an_admin_client_keeps_its_id_and_forgets_its_server(uow):
    """UPS-41: same origin, new path: id, grant and secret stay; endpoints and scopes go."""
    server, _ = seed_member(uow)
    store_client(uow, server, ClientIdentification.PREREGISTERED, secret="enc")

    await servers(uow).upsert(write("https://seo.example/v2/mcp"), actor=ADMIN)

    client = await uow.upstream_clients.for_server(server.id)
    assert client is not None and client.client_id == "cid"
    assert client.client_secret_encrypted == "enc"
    assert client.metadata_.is_admin_stored
    assert client.metadata_.grant == UpstreamGrant.AUTHORIZATION_CODE
    assert client.metadata_.remembered_endpoints is None
    assert client.metadata_.step_up_scopes == ()


async def test_ups41_the_revocation_is_audited_without_values(uow):
    """UPS-41: one management record naming the admin, with no token in it."""
    server, _ = seed_member(uow)
    await connect_users(uow, server)

    await servers(uow).upsert(write(NEW_URL), actor=ADMIN)

    [record] = await management_records(uow)
    assert record.action == "upstream.credentials_revoked"
    assert record.user_id == uuid.UUID(ADMIN.user_id) and record.api_key_id is None
    assert "t-a" not in record.model_dump_json() and "shared" not in record.model_dump_json()


async def test_ups41_case_and_a_trailing_slash_revoke_nothing(uow):
    """UPS-41: the same resource written differently keeps tokens and client, unaudited."""
    server, _ = seed_member(uow)
    await connect_users(uow, server)
    store_client(uow, server, ClientIdentification.DYNAMIC_REGISTRATION)

    await servers(uow).upsert(write("https://SEO.Example/mcp/"), actor=ADMIN)

    assert len(await uow.upstream_tokens.for_server(server.id)) == 3
    assert await uow.upstream_clients.for_server(server.id) is not None
    assert await management_records(uow) == []


async def test_ups41_a_server_without_credentials_moves_unaudited(uow):
    """UPS-41: nothing to revoke, nothing recorded."""
    await servers(uow).upsert(ServerUpsert(name="plain", url=OLD_URL))
    await servers(uow).upsert(ServerUpsert(name="plain", url=NEW_URL), actor=ADMIN)
    assert await management_records(uow) == []


async def test_ups41_ups42_a_refused_write_revokes_nothing(uow):
    """UPS-41, UPS-42: the origin move without header values is refused; all stays as it was."""
    await servers(uow).upsert(
        ServerUpsert(name="crm", url=OLD_URL, static_headers={"Authorization": "Bearer k"})
    )
    server = await uow.servers.by_name("crm")
    await connect_users(uow, server)

    with pytest.raises(ConflictError, match="UPS-42"):
        await servers(uow).upsert(ServerUpsert(name="crm", url=NEW_URL), actor=ADMIN)

    stored = await uow.servers.by_name("crm")
    assert stored.url == OLD_URL and stored.static_headers == {"Authorization": "Bearer k"}
    assert len(await uow.upstream_tokens.for_server(server.id)) == 3
    assert await management_records(uow) == []


async def test_ups42_re_entered_headers_move_with_the_server(uow):
    """UPS-42: the write that carries the header values moves the server."""
    await servers(uow).upsert(
        ServerUpsert(name="crm", url=OLD_URL, static_headers={"Authorization": "Bearer k"})
    )
    await servers(uow).upsert(
        ServerUpsert(name="crm", url=NEW_URL, static_headers={"Authorization": "Bearer new"})
    )
    stored = await uow.servers.by_name("crm")
    assert stored.url == NEW_URL and stored.static_headers == {"Authorization": "Bearer new"}


async def test_ups42_a_new_path_on_the_same_origin_keeps_the_headers(uow):
    """UPS-42: only an origin move asks for the values again."""
    await servers(uow).upsert(
        ServerUpsert(name="crm", url=OLD_URL, static_headers={"Authorization": "Bearer k"})
    )
    await servers(uow).upsert(ServerUpsert(name="crm", url="https://seo.example/v2/mcp"))
    stored = await uow.servers.by_name("crm")
    assert stored.static_headers == {"Authorization": "Bearer k"}


async def test_ups42_an_admin_client_secret_is_cleared_on_an_origin_move(uow):
    """UPS-42: the admin's client stays without its secret until it is stored again."""
    server, _ = seed_member(uow)
    store_client(uow, server, ClientIdentification.PREREGISTERED, secret="enc")

    await servers(uow).upsert(write(NEW_URL), actor=ADMIN)

    client = await uow.upstream_clients.for_server(server.id)
    assert client is not None and client.client_id == "cid"
    assert client.client_secret_encrypted is None
    [record] = await management_records(uow)
    assert record.action == "upstream.credentials_revoked"
