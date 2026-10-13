"""The real upstream OAuth provider: discovery and token requests under the egress policy.

SEC-1 covers the whole chain, including the URLs the remote side names.
"""

import json

import httpx
import pytest
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect
from bundlemcp.domain.upstream_oauth.upstream_metadata import UpstreamMetadata
from bundlemcp.infrastructure.config.settings import EnvSettings
from bundlemcp.infrastructure.httpx.upstream_oauth_provider import HttpxUpstreamProvider

# Literal private addresses pass the egress policy without a DNS lookup.
SERVER_URL = "http://10.0.0.5/mcp"
AS_URL = "http://10.0.0.6"


class FakeUpstream:
    def __init__(self, authorization_server: str = AS_URL) -> None:
        self.authorization_server = authorization_server
        self.requests: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        if request.url.path == "/.well-known/oauth-protected-resource":
            return httpx.Response(200, json={"authorization_servers": [self.authorization_server]})
        if request.url.path == "/.well-known/oauth-authorization-server":
            return httpx.Response(
                200,
                json={
                    "issuer": AS_URL,
                    "authorization_endpoint": f"{AS_URL}/authorize",
                    "token_endpoint": f"{AS_URL}/token",
                    "code_challenge_methods_supported": ["S256"],
                },
            )
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "at", "expires_in": 60})
        return httpx.Response(404)

    def provider(self) -> HttpxUpstreamProvider:
        return HttpxUpstreamProvider(
            EnvSettings(_env_file=None),
            client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(self.handler)),
        )


async def test_discovery_follows_the_protected_resource_chain():
    """UPS-25: RFC 9728 document -> RFC 8414 metadata at the named authorization server."""
    upstream = FakeUpstream()
    meta = await upstream.provider().discover(SERVER_URL)
    assert meta.token_endpoint == f"{AS_URL}/token" and meta.issuer == AS_URL
    assert upstream.requests[-1] == f"{AS_URL}/.well-known/oauth-authorization-server"


async def test_authorization_server_on_blocked_range_is_not_followed():
    """SEC-1: a document naming a metadata-service address is refused before it is fetched."""
    upstream = FakeUpstream(authorization_server="http://169.254.169.254")
    with pytest.raises(NeedsConnect) as excinfo:
        await upstream.provider().discover(SERVER_URL)
    assert excinfo.value.reason == "authorization_server_denied"
    assert not any("169.254" in url for url in upstream.requests)


async def test_token_request_refused_for_blocked_token_endpoint():
    """SEC-1: the client secret is posted only where the egress policy allows."""
    upstream = FakeUpstream()
    meta = UpstreamMetadata(
        authorization_endpoint=f"{AS_URL}/authorize", token_endpoint="http://127.0.0.1/token"
    )
    with pytest.raises(NeedsConnect) as excinfo:
        await upstream.provider().exchange(
            meta,
            code="c",
            redirect_uri="http://gw/cb",
            code_verifier="v",
            client_id="cli",
            client_secret="shh",
        )
    assert excinfo.value.reason == "token_endpoint_denied"
    assert upstream.requests == []


async def test_server_origin_on_blocked_range_is_not_probed():
    upstream = FakeUpstream()
    with pytest.raises(NeedsConnect) as excinfo:
        await upstream.provider().discover("http://127.0.0.1:9000/mcp")
    assert excinfo.value.reason == "egress_denied"
    assert upstream.requests == []


KEYCLOAK = "http://10.0.0.7/realms/x"


class PathScopedUpstream:
    """seo-mcp's shape: the protected resource document exists only under the /mcp path and
    is named by the server's 401; the authorization server is a Keycloak realm."""

    def __init__(
        self, *, challenge: bool = True, registration: bool = True, challenge_scope: str = ""
    ) -> None:
        self.challenge = challenge
        self.challenge_scope = challenge_scope
        self.registration = registration
        self.requests: list[str] = []
        self.registrations: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        if url == SERVER_URL:
            headers = (
                {
                    "WWW-Authenticate": 'Bearer error="invalid_token", resource_metadata='
                    '"http://10.0.0.5/.well-known/oauth-protected-resource/mcp"'
                    + (f', scope="{self.challenge_scope}"' if self.challenge_scope else "")
                }
                if self.challenge
                else {}
            )
            return httpx.Response(401, headers=headers)
        if url == "http://10.0.0.5/.well-known/oauth-protected-resource/mcp":
            return httpx.Response(
                200,
                json={
                    "resource": SERVER_URL,
                    "authorization_servers": [KEYCLOAK],
                    "scopes_supported": ["openid"],
                },
            )
        if url == "http://10.0.0.7/.well-known/oauth-authorization-server/realms/x":
            body = {
                "issuer": KEYCLOAK,
                "authorization_endpoint": f"{KEYCLOAK}/protocol/openid-connect/auth",
                "token_endpoint": f"{KEYCLOAK}/protocol/openid-connect/token",
                # Keycloak lists every scope in the realm, most never granted to a new client
                "scopes_supported": ["openid", "basic", "service_account", "organization"],
                "code_challenge_methods_supported": ["plain", "S256"],
            }
            if self.registration:
                body["registration_endpoint"] = f"{KEYCLOAK}/clients-registrations/openid-connect"
            return httpx.Response(200, json=body)
        if url == f"{KEYCLOAK}/clients-registrations/openid-connect":
            self.registrations.append(json.loads(request.content))
            return httpx.Response(201, json={"client_id": "registered-client"})
        return httpx.Response(404)

    def provider(self) -> HttpxUpstreamProvider:
        return HttpxUpstreamProvider(
            EnvSettings(_env_file=None),
            client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(self.handler)),
        )


async def test_discovery_follows_the_document_a_401_names():
    """UPS-25: the WWW-Authenticate resource_metadata, then RFC 8414 path insertion."""
    upstream = PathScopedUpstream()
    meta = await upstream.provider().discover(SERVER_URL)
    assert meta.issuer == KEYCLOAK
    assert meta.registration_endpoint == f"{KEYCLOAK}/clients-registrations/openid-connect"
    assert "http://10.0.0.5/.well-known/oauth-protected-resource" not in upstream.requests


async def test_requested_scopes_come_from_the_resource_not_the_authorization_server():
    """UPS-25: the resource document's scopes_supported, not Keycloak's whole catalogue."""
    meta = await PathScopedUpstream().provider().discover(SERVER_URL)
    assert meta.resource_scopes == ["openid"]
    assert meta.authorization_scope == "openid"
    assert "service_account" in meta.scopes_supported


async def test_a_challenge_scope_wins_over_the_resource_document():
    """UPS-25: the scope a 401 names is the most specific request the server makes."""
    upstream = PathScopedUpstream(challenge_scope="mcp:tools mcp:read")
    meta = await upstream.provider().discover(SERVER_URL)
    assert meta.resource_scopes == ["mcp:tools", "mcp:read"]


async def test_discovery_finds_the_path_inserted_document_without_a_challenge():
    """UPS-25: RFC 9728 puts a path-scoped resource's document under its path."""
    upstream = PathScopedUpstream(challenge=False)
    meta = await upstream.provider().discover(SERVER_URL)
    assert meta.token_endpoint == f"{KEYCLOAK}/protocol/openid-connect/token"


async def test_a_named_document_on_a_blocked_range_is_not_fetched():
    """SEC-1: the document URL comes from the remote side, so it is checked first."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            headers={"WWW-Authenticate": 'Bearer resource_metadata="http://169.254.169.254/x"'},
        )

    provider = HttpxUpstreamProvider(
        EnvSettings(_env_file=None),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(NeedsConnect) as excinfo:
        await provider.discover(SERVER_URL)
    assert excinfo.value.reason == "resource_metadata_denied"


async def test_registration_asks_for_a_public_pkce_client():
    """UPS-25: RFC 7591 registration with the gateway's callback as the only redirect URI."""
    upstream = PathScopedUpstream()
    provider = upstream.provider()
    meta = await provider.discover(SERVER_URL)
    registration = await provider.register(
        meta, redirect_uri="https://gw/oauth/upstream/callback", client_name="bundlemcp"
    )
    assert registration.client_id == "registered-client" and registration.client_secret is None
    (sent,) = upstream.registrations
    assert sent["redirect_uris"] == ["https://gw/oauth/upstream/callback"]
    assert sent["token_endpoint_auth_method"] == "none"
    assert sent["grant_types"] == ["authorization_code", "refresh_token"]


async def test_registration_endpoint_on_blocked_range_is_refused():
    upstream = FakeUpstream()
    meta = UpstreamMetadata(
        authorization_endpoint=f"{AS_URL}/authorize",
        token_endpoint=f"{AS_URL}/token",
        registration_endpoint="http://127.0.0.1/register",
    )
    with pytest.raises(NeedsConnect) as excinfo:
        await upstream.provider().register(meta, redirect_uri="https://gw/cb", client_name="b")
    assert excinfo.value.reason == "registration_endpoint_denied"
    assert upstream.requests == []


class CompliantUpstream:
    """A 2026-era server: POST-only (GET is 405), challenge names its document."""

    def __init__(self, **metadata) -> None:
        self.metadata = {
            "issuer": KEYCLOAK,
            "authorization_endpoint": f"{KEYCLOAK}/auth",
            "token_endpoint": f"{KEYCLOAK}/token",
            "registration_endpoint": f"{KEYCLOAK}/register",
            "code_challenge_methods_supported": ["S256"],
            "client_id_metadata_document_supported": True,
            "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
            "grant_types_supported": ["authorization_code", "client_credentials"],
            **metadata,
        }
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if url == SERVER_URL:
            if request.method != "POST":
                return httpx.Response(405)
            return httpx.Response(
                401,
                headers={
                    "WWW-Authenticate": 'Bearer resource_metadata="http://10.0.0.5/prm", '
                    'scope="files:read"'
                },
            )
        if url == "http://10.0.0.5/prm":
            return httpx.Response(
                200, json={"resource": "http://10.0.0.5", "authorization_servers": [KEYCLOAK]}
            )
        if url == "http://10.0.0.7/.well-known/oauth-authorization-server/realms/x":
            return httpx.Response(200, json=self.metadata)
        if url == f"{KEYCLOAK}/register":
            return httpx.Response(201, json={"client_id": "c"})
        if url == f"{KEYCLOAK}/token":
            return httpx.Response(200, json={"access_token": "at", "expires_in": 60})
        return httpx.Response(404)

    def provider(self) -> HttpxUpstreamProvider:
        return HttpxUpstreamProvider(
            EnvSettings(_env_file=None),
            client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(self.handler)),
        )


async def test_ups25_the_challenge_is_a_post_so_a_stateless_server_answers_it():
    """UPS-25: a GET would meet 405 from a stateless server before any challenge."""
    upstream = CompliantUpstream()
    meta = await upstream.provider().discover(SERVER_URL)
    first = upstream.requests[0]
    assert first.method == "POST"
    assert json.loads(first.content)["method"] == "server/discover"
    assert first.headers["mcp-method"] == "server/discover"
    assert meta.resource_scopes == ["files:read"]
    assert meta.client_id_metadata_document_supported
    assert "client_credentials" in meta.grant_types_supported


async def test_ups36_every_request_names_the_resource():
    upstream = CompliantUpstream()
    provider = upstream.provider()
    meta = await provider.discover(SERVER_URL)
    assert meta.resource == "http://10.0.0.5"  # the document's identifier covers /mcp
    url = provider.authorize_url(
        meta, client_id="c", redirect_uri="https://gw/cb", state="s", code_challenge="x", scope=None
    )
    assert "resource=http%3A%2F%2F10.0.0.5" in url
    await provider.exchange(
        meta,
        code="c",
        redirect_uri="https://gw/cb",
        code_verifier="v",
        client_id="c",
        client_secret=None,
    )
    await provider.refresh(meta, refresh_token="rt", client_id="c", client_secret=None)
    token_requests = [r for r in upstream.requests if str(r.url) == f"{KEYCLOAK}/token"]
    assert len(token_requests) == 2
    assert all(b"resource=http%3A%2F%2F10.0.0.5" in r.content for r in token_requests)


async def test_ups25_registration_names_the_application_type():
    upstream = CompliantUpstream()
    provider = upstream.provider()
    meta = await provider.discover(SERVER_URL)
    await provider.register(meta, redirect_uri="https://gw/cb", client_name="bundlemcp")
    (sent,) = [r for r in upstream.requests if str(r.url) == f"{KEYCLOAK}/register"]
    assert json.loads(sent.content)["application_type"] == "web"


async def test_ups37_metadata_without_pkce_is_refused():
    upstream = CompliantUpstream(code_challenge_methods_supported=["plain"])
    with pytest.raises(NeedsConnect) as excinfo:
        await upstream.provider().discover(SERVER_URL)
    assert excinfo.value.reason == "pkce_not_supported"


async def test_ups37_metadata_naming_another_issuer_is_refused():
    upstream = CompliantUpstream(issuer="http://10.0.0.99/realms/x")
    with pytest.raises(NeedsConnect) as excinfo:
        await upstream.provider().discover(SERVER_URL)
    assert excinfo.value.reason == "issuer_mismatch"


async def test_ups35_client_credentials_grant_sends_secret_scope_and_resource():
    upstream = CompliantUpstream()
    provider = upstream.provider()
    meta = await provider.discover(SERVER_URL)
    tokens = await provider.client_credentials(
        meta, client_id="machine", client_secret="shh", scope="files:read"
    )
    assert tokens.access_token == "at"
    (sent,) = [r for r in upstream.requests if str(r.url) == f"{KEYCLOAK}/token"]
    body = dict(pair.split("=") for pair in sent.content.decode().split("&"))
    assert body["grant_type"] == "client_credentials"
    assert body["client_id"] == "machine" and body["client_secret"] == "shh"
    assert body["scope"] == "files%3Aread" and body["resource"] == "http%3A%2F%2F10.0.0.5"
