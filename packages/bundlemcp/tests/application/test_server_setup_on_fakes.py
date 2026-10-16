"""Guided server setup and upstream credential use cases on the in-memory fakes.

UPS-1, UPS-10..UPS-15, UPS-25, UPS-34, UPS-35, UPS-37, AUTH-32.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from bundlemcp.application.contracts.upstream.upstream_probe import ProbeResult
from bundlemcp.application.delegation.delegated_token_issuer import DelegatedTokenIssuer
from bundlemcp.application.discovery.connection_diagnoser import ConnectionDiagnoser
from bundlemcp.application.discovery.discovery_service import DiscoveryService
from bundlemcp.application.errors import PreconditionError
from bundlemcp.application.management.server_inspection_service import ServerInspectionService
from bundlemcp.application.management.server_json_importer import ServerJsonImporter
from bundlemcp.application.management.server_service import ServerService
from bundlemcp.application.management.upstream_oauth_config_service import (
    UpstreamOAuthConfigService,
)
from bundlemcp.application.schemas import (
    ServerInspectRequest,
    ServerUpsert,
    UpstreamOAuthConfig,
)
from bundlemcp.application.upstream_oauth.upstream_credential_resolver import (
    UpstreamCredentialResolver,
)
from bundlemcp.application.upstream_oauth.upstream_token_service import UpstreamTokenService
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.access.user import User
from bundlemcp.domain.servers.connection_state import ConnectionState
from bundlemcp.domain.servers.identity_mode import IdentityMode
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.observed_response import ObservedResponse
from bundlemcp.domain.servers.probe_failure import ProbeFailure
from bundlemcp.domain.servers.probed_server_info import ProbedServerInfo
from bundlemcp.domain.servers.probed_tool import ProbedTool
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode
from bundlemcp.domain.shared.sha256_secret_hasher import Sha256SecretHasher
from bundlemcp.domain.upstream_oauth.client_identification import ClientIdentification
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect
from bundlemcp.domain.upstream_oauth.upstream_challenge import UpstreamChallenge
from bundlemcp.domain.upstream_oauth.upstream_client_registration import (
    UpstreamClientRegistration,
)
from bundlemcp.domain.upstream_oauth.upstream_metadata import UpstreamMetadata
from bundlemcp.domain.upstream_oauth.upstream_tokens import UpstreamTokens
from bundlemcp.infrastructure.crypto.token_cipher import TokenCipher
from bundlemcp.infrastructure.memory.in_memory_delegated_token_store import (
    InMemoryDelegatedTokenStore,
)
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
    InMemoryUnitOfWorkFactory,
)
from bundlemcp.infrastructure.memory.manual_clock import ManualClock
from bundlemcp.infrastructure.memory.noop_tool_discovery import NoopToolDiscovery
from bundlemcp.infrastructure.memory.sequential_secret_generator import SequentialSecretGenerator
from cryptography.fernet import Fernet

from tests.application.upstream_health_on_fakes import health_on

PUBLIC_BASE = "https://gw.example"
DOCUMENT_URL = f"{PUBLIC_BASE}/oauth/upstream/client.json"
CALLBACK = f"{PUBLIC_BASE}/oauth/upstream/callback"
OAUTH_CHALLENGE = (
    'Bearer resource_metadata="https://api.example/.well-known/oauth-protected-resource"'
)


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


class NoLock:
    async def acquire(self, key: str, *, ttl_seconds: int) -> bool:
        return True

    async def release(self, key: str) -> None:
        return None


class Provider:
    """An upstream authorization server whose metadata a test shapes."""

    def __init__(self, **metadata) -> None:
        self.metadata = {
            "authorization_endpoint": "https://as.example/authorize",
            "token_endpoint": "https://as.example/token",
            "issuer": "https://as.example",
            "resource_scopes": ["files:read"],
            **metadata,
        }
        self.oauth = True
        self.registered = 0
        self.scopes: list[str | None] = []
        self.client_ids: list[str] = []
        self.grants: list[dict] = []

    async def discover(self, server_url):
        if not self.oauth:
            raise NeedsConnect("upstream", "no_oauth_metadata")
        return UpstreamMetadata(**self.metadata)

    async def register(self, meta, *, redirect_uri, client_name):
        self.registered += 1
        return UpstreamClientRegistration(client_id=f"dcr-{self.registered}")

    def authorize_url(self, meta, *, client_id, redirect_uri, state, code_challenge, scope):
        self.scopes.append(scope)
        self.client_ids.append(client_id)
        return f"{meta.authorization_endpoint}?client_id={client_id}"

    async def exchange(self, meta, **kw):
        return UpstreamTokens(access_token="at", refresh_token="rt", expires_in=3600)

    async def refresh(self, meta, **kw):
        return UpstreamTokens(access_token="at2", expires_in=3600)

    async def client_credentials(self, meta, *, client_id, client_secret, scope):
        self.grants.append({"client_id": client_id, "scope": scope, "resource": meta.resource})
        return UpstreamTokens(access_token="machine-token", expires_in=3600)


class ScriptedProbe:
    """Answers per URL: a ProbeResult, or a ProbeFailure to raise."""

    def __init__(self, answers: dict[str, ProbeResult | ProbeFailure]) -> None:
        self.answers = answers
        self.seen: list[tuple[str, dict[str, str]]] = []

    async def probe(self, server, headers):
        self.seen.append((server.url, dict(server.static_headers)))
        answer = self.answers.get(server.url)
        if answer is None:
            raise ProbeFailure("refused", state=ConnectionState.NOT_MCP)
        if isinstance(answer, ProbeFailure):
            raise answer
        return answer


def ready(name: str = "Weather", description: str | None = "Forecasts") -> ProbeResult:
    return ProbeResult(
        tools=[ProbedTool(name="forecast")],
        capabilities={"tools": {}},
        protocol_version="2026-07-28",
        server_info=ProbedServerInfo(name=name, description=description),
    )


def refused(status: int, header: str | None = None) -> ProbeFailure:
    observed = ObservedResponse(status=status, challenge=UpstreamChallenge.parse(header))
    state = ConnectionState.OAUTH_REQUIRED if header else ConnectionState.CREDENTIAL_REQUIRED
    return ProbeFailure(f"HTTP {status}", state=state, observed=observed)


def inspector(uow, probe, provider=None, public_base=PUBLIC_BASE) -> ServerInspectionService:
    return ServerInspectionService(
        uow, probe, ConnectionDiagnoser(provider), public_base=public_base
    )


def tokens(uow, provider, *, document=True, cipher=None) -> UpstreamTokenService:
    return UpstreamTokenService(
        InMemoryUnitOfWorkFactory(uow),
        cipher or _cipher(),
        NoLock(),
        provider,
        metadata_document_url=DOCUMENT_URL if document else None,
    )


def _cipher() -> TokenCipher:
    return TokenCipher([Fernet.generate_key().decode()])


class _Registry:
    configured = True

    async def status(self, server_id, user_id):
        return None

    async def disconnect(self, server_id, user_id):
        return None

    async def connect_as_client(self, server):
        return None


def oauth_server(uow, identity_mode=IdentityMode.SHARED) -> McpServer:
    server = McpServer(
        name="files",
        url="https://api.example/mcp",
        auth_mode=ServerAuthMode.UPSTREAM_OAUTH,
        identity_mode=identity_mode,
    )
    uow.servers.add(server)
    return server


# --- inspection -----------------------------------------------------------------


async def test_ups11_an_open_server_is_ready_and_named_after_itself(uow):
    probe = ScriptedProbe({"https://weather.example/mcp": ready()})
    result = await inspector(uow, probe).inspect(
        ServerInspectRequest(url="https://weather.example/mcp")
    )
    assert result.connection_state == ConnectionState.READY
    assert result.tool_names == ["forecast"]
    assert result.suggestion.name == "weather"
    assert result.suggestion.description == "Forecasts"
    assert result.suggestion.auth_mode == ServerAuthMode.NONE
    assert result.suggestion.send_identity_header is False  # a public host


async def test_ups11_a_taken_name_is_not_suggested_twice(uow):
    uow.servers.add(McpServer(name="weather", url="http://other/mcp"))
    probe = ScriptedProbe({"https://weather.example/mcp": ready()})
    result = await inspector(uow, probe).inspect(
        ServerInspectRequest(url="https://weather.example/mcp")
    )
    assert result.suggestion.name == "weather-2"


async def test_ups11_a_refusal_without_oauth_metadata_asks_for_a_key(uow):
    probe = ScriptedProbe({"https://keyed.example/mcp": refused(401, 'Bearer realm="x"')})
    probe.answers["https://keyed.example/mcp"] = ProbeFailure(
        "HTTP 401", state=ConnectionState.CREDENTIAL_REQUIRED
    )
    provider = Provider()
    provider.oauth = False
    result = await inspector(uow, probe, provider).inspect(
        ServerInspectRequest(url="https://keyed.example/mcp")
    )
    assert result.connection_state == ConnectionState.CREDENTIAL_REQUIRED
    assert result.suggestion.auth_mode == ServerAuthMode.STATIC_HEADERS
    assert "API key" in result.hints[0]


async def test_ups11_candidate_headers_are_tried_and_never_echoed(uow):
    probe = ScriptedProbe({"https://keyed.example/mcp": ready()})
    result = await inspector(uow, probe).inspect(
        ServerInspectRequest(url="https://keyed.example/mcp", headers={"x-api-key": "sekrit-value"})
    )
    assert probe.seen == [("https://keyed.example/mcp", {"x-api-key": "sekrit-value"})]
    assert result.suggestion.auth_mode == ServerAuthMode.STATIC_HEADERS
    assert result.suggestion.static_headers == {}
    assert "sekrit-value" not in result.model_dump_json()


async def test_ups11_oauth_reports_how_the_gateway_identifies_itself(uow):
    probe = ScriptedProbe({"https://api.example/mcp": refused(401, OAUTH_CHALLENGE)})
    provider = Provider(
        client_id_metadata_document_supported=True, grant_types_supported=["client_credentials"]
    )
    result = await inspector(uow, probe, provider).inspect(
        ServerInspectRequest(url="https://api.example/mcp")
    )
    assert result.connection_state == ConnectionState.OAUTH_REQUIRED
    assert result.oauth is not None
    assert result.oauth.client_identification == ClientIdentification.METADATA_DOCUMENT
    assert result.oauth.supports_client_credentials
    assert result.oauth.scopes == ["files:read"]
    assert result.suggestion.auth_mode == ServerAuthMode.UPSTREAM_OAUTH
    assert result.suggestion.identity_mode == IdentityMode.PER_USER


async def test_ups11_oauth_without_automatic_registration_says_what_to_register(uow):
    probe = ScriptedProbe({"https://api.example/mcp": refused(401, OAUTH_CHALLENGE)})
    result = await inspector(uow, probe, Provider()).inspect(
        ServerInspectRequest(url="https://api.example/mcp")
    )
    assert result.oauth.client_identification == ClientIdentification.PREREGISTERED_REQUIRED
    assert CALLBACK in result.hints[0]


async def test_ups11_a_url_missing_its_mcp_path_is_found(uow):
    probe = ScriptedProbe({"https://weather.example/mcp": ready()})
    result = await inspector(uow, probe).inspect(
        ServerInspectRequest(url="https://weather.example")
    )
    assert result.connection_state == ConnectionState.READY
    assert result.suggested_url == "https://weather.example/mcp"
    assert result.suggestion.url == "https://weather.example/mcp"


async def test_ups11_an_sse_url_is_explained(uow):
    probe = ScriptedProbe({})
    result = await inspector(uow, probe).inspect(
        ServerInspectRequest(url="https://old.example/sse")
    )
    assert result.connection_state == ConnectionState.NOT_MCP
    assert "SSE" in result.hints[0]
    assert len(probe.seen) == 1  # no /mcp guess for an explicit transport path


# --- server.json import ---------------------------------------------------------


def test_ups15_a_server_json_draft_carries_the_declared_headers():
    draft = ServerJsonImporter().draft(
        {
            "name": "io.github.acme/weather",
            "description": "Weather forecasts",
            "remotes": [
                {"type": "sse", "url": "https://acme.example/sse"},
                {
                    "type": "streamable-http",
                    "url": "https://{region}.acme.example/mcp",
                    "headers": [
                        {
                            "name": "X-API-Key",
                            "description": "From your dashboard",
                            "isRequired": True,
                            "isSecret": True,
                        }
                    ],
                },
            ],
        }
    )
    assert draft.name == "weather"
    assert draft.url == "https://{region}.acme.example/mcp"
    assert draft.url_variables == ["region"]
    assert [(h.name, h.is_required, h.is_secret) for h in draft.headers] == [
        ("X-API-Key", True, True)
    ]
    assert draft.problems == []


def test_ups15_a_local_only_or_sse_only_document_is_reported():
    assert ServerJsonImporter().draft({"name": "x", "packages": [{}]}).problems
    sse_only = ServerJsonImporter().draft(
        {"name": "x", "remotes": [{"type": "sse", "url": "https://x/sse"}]}
    )
    assert sse_only.url is None and "sse" in sse_only.problems[0]


# --- registration rules ------------------------------------


async def test_ups13_identity_header_defaults_by_network_and_is_kept_on_update(uow):
    servers = ServerService(uow, discovery=NoopToolDiscovery(), public_base="http://gw")
    internal = await servers.upsert(ServerUpsert(name="gsc", url="http://seo-gsc:8000/mcp"))
    external = await servers.upsert(ServerUpsert(name="lin", url="https://mcp.linear.app/mcp"))
    assert internal.send_identity_header is True
    assert external.send_identity_header is False
    await servers.upsert(
        ServerUpsert(name="lin", url="https://mcp.linear.app/mcp", send_identity_header=True)
    )
    kept = await servers.upsert(ServerUpsert(name="lin", url="https://mcp.linear.app/mcp"))
    assert kept.send_identity_header is True


async def test_ups10_an_update_without_protocol_mode_keeps_the_pin(uow):
    servers = ServerService(uow, discovery=NoopToolDiscovery(), public_base="http://gw")
    await servers.upsert(ServerUpsert(name="old", url="http://old/mcp", protocol_mode="legacy"))
    kept = await servers.upsert(ServerUpsert(name="old", url="http://old/mcp", description="d"))
    assert kept.protocol_mode == "legacy"


async def test_ups1_auth_mode_follows_the_stored_headers(uow):
    servers = ServerService(uow, discovery=NoopToolDiscovery(), public_base="http://gw")
    keyed = await servers.upsert(
        ServerUpsert(name="k", url="http://k/mcp", static_headers={"x-api-key": "v"})
    )
    assert keyed.auth_mode == ServerAuthMode.STATIC_HEADERS
    # headers are write-only: an update without them keeps them, and the mode with them
    again = await servers.upsert(ServerUpsert(name="k", url="http://k/mcp"))
    assert again.auth_mode == ServerAuthMode.STATIC_HEADERS


def test_ups14_denied_forward_headers_are_refused_at_write_time():
    with pytest.raises(ValueError, match="cookie"):
        ServerUpsert(name="s", url="http://s/mcp", forward_headers={"cookie": "cookie"})


async def test_ups35_a_client_credentials_server_cannot_become_per_user(uow):
    server = oauth_server(uow)
    config = UpstreamOAuthConfigService(uow, cipher=_cipher(), connections=_Registry())
    await config.set_client(
        "files",
        UpstreamOAuthConfig(
            client_id="machine", client_secret="s", grant_type="client_credentials"
        ),
    )
    servers = ServerService(uow, discovery=NoopToolDiscovery(), public_base="http://gw")
    with pytest.raises(PreconditionError):
        await servers.upsert(
            ServerUpsert(
                name="files",
                url=server.url,
                auth_mode=ServerAuthMode.UPSTREAM_OAUTH,
                identity_mode=IdentityMode.PER_USER,
            )
        )


async def test_ups35_a_client_credentials_client_needs_a_secret_and_a_shared_server(uow):
    oauth_server(uow, IdentityMode.PER_USER)
    config = UpstreamOAuthConfigService(uow, cipher=_cipher(), connections=_Registry())
    with pytest.raises(PreconditionError, match="shared"):
        await config.set_client(
            "files",
            UpstreamOAuthConfig(
                client_id="machine", client_secret="s", grant_type="client_credentials"
            ),
        )


# --- discovery records the connection state -------------------------------------


async def test_ups12_discovery_records_what_each_probe_found(uow):
    server = McpServer(name="api", url="https://api.example/mcp")
    uow.servers.add(server)
    probe = ScriptedProbe({"https://api.example/mcp": refused(401, OAUTH_CHALLENGE)})
    service = DiscoveryService(
        InMemoryUnitOfWorkFactory(uow),
        probe,
        health=health_on(uow),
        diagnoser=ConnectionDiagnoser(Provider()),
    )
    result = await service.discover(server.id)
    assert result.connection_state == ConnectionState.OAUTH_REQUIRED
    stored = await uow.servers.get(server.id)
    assert stored.connection_state == ConnectionState.OAUTH_REQUIRED
    assert stored.configuration_mismatch is not None
    probe.answers["https://api.example/mcp"] = ready()
    await service.discover(server.id)
    assert (await uow.servers.get(server.id)).connection_state == ConnectionState.READY


async def test_ups12_a_refused_key_is_not_mistaken_for_oauth(uow):
    """A server sending a credential that is refused has a bad credential, not OAuth."""
    server = McpServer(name="k", url="https://k.example/mcp", static_headers={"x-api-key": "old"})
    uow.servers.add(server)
    probe = ScriptedProbe({"https://k.example/mcp": refused(401)})
    service = DiscoveryService(
        InMemoryUnitOfWorkFactory(uow),
        probe,
        health=health_on(uow),
        diagnoser=ConnectionDiagnoser(Provider()),
    )
    result = await service.discover(server.id)
    assert result.connection_state == ConnectionState.CREDENTIAL_REQUIRED


# --- how the gateway identifies itself upstream ----------------------------


async def test_ups25_a_metadata_document_is_preferred_over_registration(uow):
    server = oauth_server(uow)
    provider = Provider(
        client_id_metadata_document_supported=True,
        registration_endpoint="https://as.example/register",
    )
    await tokens(uow, provider).build_authorize(server, CALLBACK, "state")
    assert provider.client_ids == [DOCUMENT_URL]
    assert provider.registered == 0


async def test_ups25_registration_is_used_when_no_document_can_be(uow):
    server = oauth_server(uow)
    provider = Provider(
        client_id_metadata_document_supported=True,
        registration_endpoint="https://as.example/register",
    )
    await tokens(uow, provider, document=False).build_authorize(server, CALLBACK, "state")
    assert provider.client_ids == ["dcr-1"]


async def test_ups25_without_either_the_admin_must_store_a_client(uow):
    server = oauth_server(uow)
    with pytest.raises(NeedsConnect) as excinfo:
        await tokens(uow, Provider()).build_authorize(server, CALLBACK, "state")
    assert excinfo.value.reason == "no_client_config"


async def test_ups37_a_new_issuer_discards_the_registration_and_its_tokens(uow):
    server = oauth_server(uow)
    provider = Provider(registration_endpoint="https://as.example/register")
    service = tokens(uow, provider)
    await service.build_authorize(server, CALLBACK, "state")
    await service.complete_authorize(
        server, None, code="c", code_verifier="v", redirect_uri=CALLBACK
    )
    assert await uow.upstream_tokens.find(server.id, None) is not None

    provider.metadata["issuer"] = "https://moved.example"
    await service.build_authorize(server, CALLBACK, "state")
    assert provider.client_ids == ["dcr-1", "dcr-2"]
    assert await uow.upstream_tokens.find(server.id, None) is None


async def test_ups37_an_admin_client_is_never_replaced(uow):
    server = oauth_server(uow)
    provider = Provider(registration_endpoint="https://as.example/register")
    config = UpstreamOAuthConfigService(uow, cipher=_cipher(), connections=_Registry())
    await config.set_client("files", UpstreamOAuthConfig(client_id="admin-client"))
    provider.metadata["issuer"] = "https://moved.example"
    await tokens(uow, provider).build_authorize(server, CALLBACK, "state")
    assert provider.client_ids == ["admin-client"]
    assert provider.registered == 0


# --- step-up and client credentials ---------------------------------------


async def test_ups34_demanded_scopes_are_requested_at_the_next_connect(uow):
    server = oauth_server(uow)
    provider = Provider(registration_endpoint="https://as.example/register")
    service = tokens(uow, provider)
    await service.build_authorize(server, CALLBACK, "state")
    assert await service.request_step_up(server, ["files:write"])
    assert not await service.request_step_up(server, ["files:write"])  # nothing new
    await service.build_authorize(server, CALLBACK, "state")
    assert provider.scopes == ["files:read", "files:read files:write"]


async def test_ups35_client_credentials_obtain_the_shared_token_without_a_browser(uow):
    server = oauth_server(uow)
    provider = Provider()
    cipher = _cipher()
    service = tokens(uow, provider, cipher=cipher)
    config = UpstreamOAuthConfigService(uow, cipher=cipher, connections=_Registry())
    await config.set_client(
        "files",
        UpstreamOAuthConfig(
            client_id="machine", client_secret="s", grant_type="client_credentials"
        ),
    )
    token = await service.ensure_access_token(server, None)
    assert token == "machine-token"
    assert provider.grants == [
        {"client_id": "machine", "scope": "files:read", "resource": "https://api.example/mcp"}
    ]
    with pytest.raises(NeedsConnect):
        await service.build_authorize(server, CALLBACK, "state")


# --- delegated tokens --------------------------------------------------------------


async def test_auth32_a_delegated_server_gets_a_token_bound_to_it():
    store = InMemoryDelegatedTokenStore()
    clock = ManualClock(datetime(2026, 9, 24, tzinfo=UTC))
    issuer = DelegatedTokenIssuer(
        store, clock=clock, generator=SequentialSecretGenerator(), hasher=Sha256SecretHasher()
    )
    server = McpServer(
        name="gsc", url="http://seo-gsc:8000/mcp", auth_mode=ServerAuthMode.DELEGATED_TOKEN
    )
    resolver = UpstreamCredentialResolver(None, PUBLIC_BASE, delegated=issuer)
    user = CallerIdentity.oauth_user(
        User(id=uuid_of("u1"), oidc_issuer="http://idp", oidc_sub="u1", email="u@example.com")
    )
    headers = await resolver.headers_for(server, user, endpoint="main")
    token = headers["Authorization"].removeprefix("Bearer ")
    assert token.startswith("bmcp_dt_")
    record = await issuer.resolve(token)
    assert record is not None
    assert (record.sub, record.audience, record.actor) == (
        str(uuid_of("u1")),
        "http://seo-gsc:8000/mcp",
        "endpoint:main",
    )
    assert token not in str(store.records)  # only the hash is kept
    # a fresh token for every call
    again = await resolver.headers_for(server, user, endpoint="main")
    assert again != headers
    # anonymous callers get none; expired tokens stop resolving
    assert await resolver.headers_for(server, CallerIdentity.anonymous()) == {}
    clock.advance(timedelta(minutes=6))
    assert await issuer.resolve(token) is None


def uuid_of(label: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, label)
