"""Upstream OAuth use cases on the in-memory fakes (spec 23: UPO-1/3, spec 11: DISC-1)."""

import uuid

import pytest
from bundlemcp.application.contracts.upstream.upstream_probe import ProbeResult
from bundlemcp.application.discovery.discovery_service import DiscoveryService
from bundlemcp.application.upstream_oauth.account_connect_prompts import AccountConnectPrompts
from bundlemcp.application.upstream_oauth.upstream_credential_resolver import (
    UpstreamCredentialResolver,
)
from bundlemcp.application.upstream_oauth.upstream_token_service import UpstreamTokenService
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.bundles.bundle import Bundle
from bundlemcp.domain.bundles.bundle_server import BundleServer
from bundlemcp.domain.bundles.bundle_view import BundleView
from bundlemcp.domain.endpoints.endpoint import Endpoint
from bundlemcp.domain.servers.health_status import HealthStatus
from bundlemcp.domain.servers.identity_mode import IdentityMode
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.probed_tool import ProbedTool
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect
from bundlemcp.domain.upstream_oauth.upstream_client_registration import (
    UpstreamClientRegistration,
)
from bundlemcp.domain.upstream_oauth.upstream_metadata import UpstreamMetadata
from bundlemcp.domain.upstream_oauth.upstream_oauth_client import UpstreamOAuthClient
from bundlemcp.domain.upstream_oauth.upstream_tokens import UpstreamTokens
from bundlemcp.infrastructure.crypto.token_cipher import TokenCipher
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
    InMemoryUnitOfWorkFactory,
)
from cryptography.fernet import Fernet

PUBLIC_BASE = "https://gw.example"
CALLBACK = f"{PUBLIC_BASE}/oauth/upstream/callback"


class NoLock:
    async def acquire(self, key: str, *, ttl_seconds: int) -> bool:
        return True

    async def release(self, key: str) -> None:
        return None


class FakeProvider:
    """An upstream authorization server; registration is on unless told otherwise."""

    def __init__(self, *, registration: bool = True) -> None:
        self.registration = registration
        self.registered: list[str] = []

    async def discover(self, server_url):
        return UpstreamMetadata(
            authorization_endpoint="https://idp/authorize",
            token_endpoint="https://idp/token",
            registration_endpoint="https://idp/register" if self.registration else None,
        )

    async def register(self, meta, *, redirect_uri, client_name):
        self.registered.append(redirect_uri)
        return UpstreamClientRegistration(client_id="dynamic-client")

    def authorize_url(self, meta, *, client_id, redirect_uri, state, code_challenge, scope):
        return f"{meta.authorization_endpoint}?client_id={client_id}&state={state}"

    async def exchange(self, meta, **kw):
        return UpstreamTokens(access_token="at", expires_in=3600)

    async def refresh(self, meta, **kw):
        return UpstreamTokens(access_token="at2", expires_in=3600)


class RecordingProbe:
    def __init__(self) -> None:
        self.headers: list[dict[str, str]] = []

    async def probe(self, server, headers):
        self.headers.append(headers)
        return ProbeResult(
            tools=[ProbedTool(name="lookup", input_schema={"type": "object"})],
            capabilities=None,
            protocol_version=None,
        )


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


def token_service(uow, provider=None) -> UpstreamTokenService:
    cipher = TokenCipher([Fernet.generate_key().decode()])
    return UpstreamTokenService(
        InMemoryUnitOfWorkFactory(uow), cipher, NoLock(), provider or FakeProvider()
    )


def seed_member(uow, identity_mode=IdentityMode.PER_USER) -> tuple[McpServer, Bundle]:
    server = McpServer(
        name="seo",
        url="https://seo.example/mcp",
        auth_mode=ServerAuthMode.UPSTREAM_OAUTH,
        identity_mode=identity_mode,
    )
    bundle = Bundle(name="marius")
    uow.servers.add(server)
    uow.bundles.add(bundle)
    uow.memberships.add(BundleServer(bundle_id=bundle.id, server_id=server.id))
    return server, bundle


def discovery(uow, tokens, probe) -> DiscoveryService:
    return DiscoveryService(
        InMemoryUnitOfWorkFactory(uow),
        probe,
        credentials=UpstreamCredentialResolver(tokens, PUBLIC_BASE),
    )


async def test_per_user_server_is_not_probed_before_anyone_connects(uow):
    """DISC-1: no account to probe with is reported, never counted as the upstream failing."""
    server, _ = seed_member(uow)
    probe = RecordingProbe()
    service = discovery(uow, token_service(uow), probe)
    for _ in range(5):
        result = await service.discover(server.id)
        assert result.error == "upstream not connected"
    assert probe.headers == []
    assert server.health_status != HealthStatus.ERROR
    assert uow.published == []


async def test_per_user_server_is_probed_with_a_connected_users_token(uow):
    """DISC-1/BND-7: a user's token lists the tools, and the server's bundles re-list."""
    server, bundle = seed_member(uow)
    tokens = token_service(uow)
    user = CallerIdentity.oauth_user(uuid.uuid4(), "u@x").user_uuid
    await tokens.save(server.id, user, UpstreamTokens(access_token="user-token", expires_in=3600))
    probe = RecordingProbe()
    service = discovery(uow, tokens, probe)

    result = await service.discover(server.id)
    assert result.error is None and result.discovered == 1
    assert probe.headers == [{"Authorization": "Bearer user-token"}]
    assert [(e.entity_type, e.key) for e in uow.published] == [("bundle", bundle.name)]

    uow.published.clear()
    await service.discover(server.id)  # nothing changed, nothing announced
    assert uow.published == []


async def test_shared_server_is_probed_with_the_shared_token(uow):
    server, _ = seed_member(uow, IdentityMode.SHARED)
    tokens = token_service(uow)
    await tokens.save(server.id, None, UpstreamTokens(access_token="shared", expires_in=3600))
    probe = RecordingProbe()
    await discovery(uow, tokens, probe).discover(server.id)
    assert probe.headers == [{"Authorization": "Bearer shared"}]


async def test_announced_discovery_re_lists_bundles_even_without_a_token(uow):
    """DISC-1: a connect always tells the bundle's clients to list again."""
    server, bundle = seed_member(uow)
    await discovery(uow, token_service(uow), RecordingProbe()).discover(server.id, announce=True)
    assert [e.key for e in uow.published] == [bundle.name]


async def test_connect_registers_the_gateway_once_when_no_client_is_stored(uow):
    """UPO-1: dynamic registration at the discovered endpoint, remembered for later connects."""
    server, _ = seed_member(uow)
    provider = FakeProvider()
    tokens = token_service(uow, provider)

    start = await tokens.build_authorize(server, CALLBACK, "state-1")
    assert "client_id=dynamic-client" in start.url
    stored = await uow.upstream_clients.for_server(server.id)
    assert stored is not None and stored.client_id == "dynamic-client"
    assert stored.metadata_["registration_endpoint"] == "https://idp/register"

    await tokens.build_authorize(server, CALLBACK, "state-2")
    assert provider.registered == [CALLBACK]  # registered exactly once


async def test_an_admin_stored_client_is_used_instead_of_registering(uow):
    server, _ = seed_member(uow)
    uow.upstream_clients.add(UpstreamOAuthClient(server_id=server.id, client_id="admin-client"))
    provider = FakeProvider()
    start = await token_service(uow, provider).build_authorize(server, CALLBACK, "s")
    assert "client_id=admin-client" in start.url
    assert provider.registered == []


async def test_without_a_registration_endpoint_the_admin_must_store_a_client(uow):
    server, _ = seed_member(uow)
    with pytest.raises(NeedsConnect) as excinfo:
        await token_service(uow, FakeProvider(registration=False)).build_authorize(
            server, CALLBACK, "s"
        )
    assert excinfo.value.reason == "no_client_config"


def view_of(server: McpServer, bundle: Bundle) -> BundleView:
    endpoint = Endpoint(name="default", bundle_id=bundle.id)
    return BundleView(endpoint=endpoint, bundle=bundle, servers={server.name: server}, tools=[])


async def test_connect_tool_is_offered_until_the_caller_connects(uow):
    """UPO-3: listed for an unconnected user only; its call hands out the ?as=me link."""
    server, bundle = seed_member(uow)
    tokens = token_service(uow)
    prompts = AccountConnectPrompts(UpstreamCredentialResolver(tokens, PUBLIC_BASE))
    view = view_of(server, bundle)
    user = CallerIdentity.oauth_user(uuid.uuid4(), "u@x")

    pending = await prompts.pending(view, user)
    assert [t.presented_name for t in pending] == ["seo__connect_account"]
    text = prompts.instructions(pending[0], user)
    assert f"{PUBLIC_BASE}/oauth/upstream/seo/connect?as=me" in text

    await tokens.save(server.id, user.user_uuid, UpstreamTokens(access_token="t"))
    assert await prompts.pending(view, user) == []
    assert prompts.resolve(view, "seo__connect_account") is not None  # still callable


async def test_connect_tool_is_not_offered_to_callers_who_cannot_connect(uow):
    """UPO-3: an API-key caller has no user to key a connection to."""
    server, bundle = seed_member(uow)
    prompts = AccountConnectPrompts(UpstreamCredentialResolver(token_service(uow), PUBLIC_BASE))
    key_caller = CallerIdentity.with_api_key(uuid.uuid4())
    assert await prompts.pending(view_of(server, bundle), key_caller) == []
