"""The connect-account tool over the MCP edge, and discovery after a connect (UPS-27, UPS-17).

A signed-in user who has not connected a per-user server sees that server's
connect tool, calls it for the link, connects in the browser, and from then on
sees the server's tools instead.
"""

from contextlib import asynccontextmanager
from datetime import timedelta

from bundlemcp.api.oauth.session_cookie import SESSION_COOKIE
from bundlemcp.domain.servers.identity_mode import IdentityMode
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode
from bundlemcp.domain.sessions.admin_session import AdminSession
from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.domain.shared.secrets import hash_token
from bundlemcp.domain.upstream_oauth.upstream_metadata import UpstreamMetadata
from bundlemcp.domain.upstream_oauth.upstream_tokens import UpstreamTokens
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.bundle_server_row import BundleServerRow
from bundlemcp.infrastructure.postgres.rows.endpoint_row import EndpointRow
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.oauth_access_token_row import OAuthAccessTokenRow
from bundlemcp.infrastructure.postgres.rows.oauth_client_row import OAuthClientRow
from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow
from bundlemcp.infrastructure.postgres.rows.upstream_oauth_client_row import UpstreamOAuthClientRow
from bundlemcp.infrastructure.postgres.rows.user_row import UserRow
from cryptography.fernet import Fernet
from fastmcp import Client, FastMCP
from mcp.types import CLIENT_CAPABILITIES_META_KEY, PROTOCOL_VERSION_META_KEY

from tests.conftest import background_probes_done, hermetic_settings, serving

KEY = Fernet.generate_key().decode()
PUBLIC_URL = "http://gw"
USER_TOKEN = "bmcp_at_user-access-token"

seo = FastMCP("seo")


@seo.tool
def keyword_volume(keyword: str) -> str:
    """Search volume for a keyword."""
    return f"volume:{keyword}"


class HeaderRecordingFactory:
    """Builds in-process upstream clients and remembers the headers each was given."""

    def __init__(self) -> None:
        self.headers: list[dict[str, str]] = []

    def __call__(self, server, extra_headers, *, observer=None, **handlers):
        self.headers.append(dict(extra_headers))
        return Client(seo)


class FakeProvider:
    async def discover(self, server_url):
        return UpstreamMetadata(
            authorization_endpoint="https://idp/a", token_endpoint="https://idp/t"
        )

    async def register(self, meta, *, redirect_uri, client_name):
        raise AssertionError("a client is already stored")

    def authorize_url(self, meta, *, client_id, redirect_uri, state, code_challenge, scope):
        return f"{meta.authorization_endpoint}?state={state}"

    async def exchange(self, meta, **kw):
        return UpstreamTokens(access_token="seo-user-token", expires_in=3600)

    async def refresh(self, meta, **kw):
        return UpstreamTokens(access_token="seo-user-token-2", expires_in=3600)

    async def client_credentials(self, meta, **kw):
        return UpstreamTokens(access_token="at-client", expires_in=3600)


async def _seed(engine, *, with_tool: bool):
    async with session_factory(engine)() as db:
        user = UserRow(oidc_issuer="i", oidc_sub="u", email="u@x")
        server = McpServerRow(
            name="seo",
            url="https://seo.example/mcp",
            auth_mode=ServerAuthMode.UPSTREAM_OAUTH,
            identity_mode=IdentityMode.PER_USER,
        )
        bundle = BundleRow(name="b")
        db.add_all([user, server, bundle])
        await db.commit()
        for row in (user, server, bundle):
            await db.refresh(row)
        endpoint = EndpointRow(name="e", bundle_id=bundle.id, auth_modes=["oauth"])
        db.add_all(
            [
                endpoint,
                BundleServerRow(bundle_id=bundle.id, server_id=server.id),
                UpstreamOAuthClientRow(server_id=server.id, client_id="cli"),
                OAuthClientRow(client_id="claude", redirect_uris=["https://c/cb"]),
            ]
        )
        if with_tool:
            db.add(
                ToolRow(
                    server_id=server.id,
                    name="keyword_volume",
                    schema_hash="h",
                    input_schema={"type": "object"},
                )
            )
        await db.commit()
        await db.refresh(endpoint)
        db.add(
            OAuthAccessTokenRow(
                access_token_hash=hash_token(USER_TOKEN),
                client_id="claude",
                user_id=user.id,
                endpoint_id=endpoint.id,
                expires_at=utcnow() + timedelta(hours=1),
            )
        )
        await db.commit()
        return user, server


@asynccontextmanager
async def _running(engine, redis, factory):
    async with serving(
        engine,
        redis,
        settings=hermetic_settings(public_url=PUBLIC_URL, token_encryption_keys=[KEY]),
        base_url=PUBLIC_URL,
        bearer=USER_TOKEN,
        follow_redirects=False,
        client_factory=factory,
        upstream_oidc_provider=FakeProvider(),
    ) as (http, app):
        yield http, app


async def _rpc(http, session, method, params=None):
    resp = await http.post(
        "/e/mcp",
        headers={"Mcp-Session-Id": session},
        json={"jsonrpc": "2.0", "id": 2, "method": method, "params": params or {}},
    )
    return resp.json()


async def _init(http) -> str:
    resp = await http.post(
        "/e/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    assert resp.status_code == 200, resp.text
    return resp.headers["mcp-session-id"]


async def _tool_names(http, session) -> list[str]:
    return [t["name"] for t in (await _rpc(http, session, "tools/list"))["result"]["tools"]]


async def test_unconnected_user_is_offered_the_connect_tool(engine, redis):
    """UPS-27: listed after the bundle's tools; calling it returns the link, no upstream reached."""
    await _seed(engine, with_tool=True)
    factory = HeaderRecordingFactory()
    async with _running(engine, redis, factory) as (http, _app):
        session = await _init(http)
        assert await _tool_names(http, session) == ["seo__keyword_volume", "seo__connect_account"]
        called = await _rpc(
            http, session, "tools/call", {"name": "seo__connect_account", "arguments": {}}
        )
    result = called["result"]
    assert result["isError"] is False
    assert f"{PUBLIC_URL}/oauth/upstream/seo/connect?as=me" in result["content"][0]["text"]
    assert factory.headers == []  # no upstream was reached


async def test_connecting_discovers_tools_and_retires_the_connect_tool(engine, redis):
    """UPS-17: the callback's token lists the tools; the user then sees them, not the prompt."""
    user, _server = await _seed(engine, with_tool=False)
    factory = HeaderRecordingFactory()
    async with _running(engine, redis, factory) as (http, app):
        session = await _init(http)
        assert await _tool_names(http, session) == ["seo__connect_account"]

        sid = await app.state.container.admin_sessions.create(
            AdminSession(user_id=str(user.id), email=user.email, is_admin=False)
        )
        http.cookies.set(SESSION_COOKIE, sid)
        start = await http.get("/oauth/upstream/seo/connect", params={"as": "me"})
        state = start.headers["location"].split("state=")[1]
        callback = await http.get("/oauth/upstream/callback", params={"code": "c", "state": state})
        assert callback.status_code == 200, callback.text

        await background_probes_done()  # discovery runs in the background after the callback
        assert await _tool_names(http, session) == ["seo__keyword_volume"]
    assert {"Authorization": "Bearer seo-user-token"} in factory.headers


async def _modern_tools_list(http) -> dict:
    body = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/list",
        "params": {
            "_meta": {
                PROTOCOL_VERSION_META_KEY: "2026-07-28",
                CLIENT_CAPABILITIES_META_KEY: {},
            }
        },
    }
    headers = {"MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "tools/list"}
    resp = await http.post("/e/mcp", headers=headers, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["result"]


async def test_prot16_a_list_with_a_connect_tool_is_private(engine, redis):
    """PROT-16: a tools/list carrying this caller's connect-account tool is cacheScope private;
    once the caller has connected, the list is the same for everyone again and public."""
    user, _server = await _seed(engine, with_tool=True)
    factory = HeaderRecordingFactory()
    async with _running(engine, redis, factory) as (http, app):
        before = await _modern_tools_list(http)
        assert "seo__connect_account" in [t["name"] for t in before["tools"]]
        assert before["cacheScope"] == "private"

        sid = await app.state.container.admin_sessions.create(
            AdminSession(user_id=str(user.id), email=user.email, is_admin=False)
        )
        http.cookies.set(SESSION_COOKIE, sid)
        start = await http.get("/oauth/upstream/seo/connect", params={"as": "me"})
        state = start.headers["location"].split("state=")[1]
        callback = await http.get("/oauth/upstream/callback", params={"code": "c", "state": state})
        assert callback.status_code == 200, callback.text

        after = await _modern_tools_list(http)
    assert [t["name"] for t in after["tools"]] == ["seo__keyword_volume"]
    assert after["cacheScope"] == "public"
