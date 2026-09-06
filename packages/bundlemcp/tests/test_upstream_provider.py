"""The real upstream OAuth provider: discovery and token requests under the egress policy.

SEC-1 covers the whole chain, including the URLs the remote side names.
"""

import httpx
import pytest
from bundlemcp.oauth.upstream_client import HttpxUpstreamProvider, NeedsConnect, UpstreamMetadata
from bundlemcp.settings import Settings

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
                },
            )
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "at", "expires_in": 60})
        return httpx.Response(404)

    def provider(self) -> HttpxUpstreamProvider:
        return HttpxUpstreamProvider(
            Settings(_env_file=None),
            client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(self.handler)),
        )


async def test_discovery_follows_the_protected_resource_chain():
    """UPO-1: RFC 9728 document -> RFC 8414 metadata at the named authorization server."""
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
