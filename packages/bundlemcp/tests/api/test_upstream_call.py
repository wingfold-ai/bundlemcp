"""Upstream OAuth call-path tests (spec 23: UPO-2/3/4/6) — bearer attach + refresh + connect error.

Uses an injected client factory that inspects the Authorization header the
gateway attaches, so the whole path is hermetic (no loopback upstream needed).
"""

from contextlib import asynccontextmanager

from bundlemcp.application.upstream_oauth.upstream_token_service import UpstreamTokenService
from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.domain.servers.identity_mode import IdentityMode
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode
from bundlemcp.domain.shared.secrets import display_prefix, hash_token
from bundlemcp.domain.upstream_oauth.upstream_metadata import UpstreamMetadata
from bundlemcp.domain.upstream_oauth.upstream_tokens import UpstreamTokens
from bundlemcp.infrastructure.config.settings import EnvSettings
from bundlemcp.infrastructure.crypto.token_cipher import token_cipher
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.api_key_row import ApiKeyRow
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.bundle_server_row import BundleServerRow
from bundlemcp.infrastructure.postgres.rows.endpoint_row import EndpointRow
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow
from bundlemcp.infrastructure.postgres.rows.upstream_oauth_client_row import UpstreamOAuthClientRow
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory
from bundlemcp.infrastructure.valkey.refresh_lock import ValkeyRefreshLock
from cryptography.fernet import Fernet
from fastmcp import Client, FastMCP
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import ENDPOINT_KEY, hermetic_settings, serving

KEY = Fernet.generate_key().decode()

up_server = FastMCP("up")


@up_server.tool
def whoami(text: str) -> str:
    """Echo."""
    return f"up:{text}"


class BearerCapturingFactory:
    """Records the Authorization header the gateway attaches; can simulate 401."""

    def __init__(self, reject: set[str] | None = None):
        self.seen: list[str | None] = []
        self.reject = reject or set()

    def __call__(self, server, extra_headers, **handlers):
        bearer = extra_headers.get("Authorization")
        self.seen.append(bearer)
        if bearer in self.reject:
            return _RaisingClient()
        return Client(up_server)


class _RaisingClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def call_tool_mcp(self, name, arguments, progress_handler=None):
        raise RuntimeError("401 Unauthorized")


class FakeUpstreamProvider:
    def __init__(self):
        self.refresh_calls = 0

    async def discover(self, server_url):
        return UpstreamMetadata(
            authorization_endpoint="https://idp/a", token_endpoint="https://idp/t"
        )

    def authorize_url(self, meta, **kw):
        return "https://idp/a"

    async def exchange(self, meta, **kw):
        return UpstreamTokens(access_token="at", expires_in=3600)

    async def refresh(self, meta, *, refresh_token, client_id, client_secret):
        self.refresh_calls += 1
        return UpstreamTokens(access_token="at-refreshed", refresh_token="rt2", expires_in=3600)


async def _seed(engine, *, identity_mode=IdentityMode.SHARED):
    async with session_factory(engine)() as db:
        db.add(
            ApiKeyRow(
                name="ep",
                key_hash=hash_token(ENDPOINT_KEY),
                key_prefix=display_prefix(ENDPOINT_KEY),
                kind=ApiKeyKind.ENDPOINT,
            )
        )
        srv = McpServerRow(
            name="up",
            url="https://up/mcp",
            auth_mode=ServerAuthMode.UPSTREAM_OAUTH,
            identity_mode=identity_mode,
        )
        bundle = BundleRow(name="b")
        db.add_all([srv, bundle])
        await db.commit()
        await db.refresh(srv)
        await db.refresh(bundle)
        db.add(UpstreamOAuthClientRow(server_id=srv.id, client_id="cli"))
        db.add(BundleServerRow(bundle_id=bundle.id, server_id=srv.id))
        db.add(ToolRow(server_id=srv.id, name="whoami", schema_hash="h", input_schema={}))
        # oauth endpoint so a per_user caller is authenticated; api_key for shared
        db.add(EndpointRow(name="e", bundle_id=bundle.id, auth_modes=["api_key"]))
        await db.commit()
        return srv


@asynccontextmanager
async def _running(engine, redis, factory, provider, *, keys=(KEY,)):
    """The gateway with an injected upstream factory and provider, and an endpoint client."""
    async with serving(
        engine,
        redis,
        settings=hermetic_settings(token_encryption_keys=list(keys)),
        bearer=ENDPOINT_KEY,
        client_factory=factory,
        upstream_oidc_provider=provider,
    ) as (http, _app):
        yield http


async def _call(http, session, args=None):
    return await http.post(
        "/e/mcp",
        headers={"Mcp-Session-Id": session},
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "up__whoami", "arguments": args or {"text": "x"}},
        },
    )


async def _init(http):
    r = await http.post(
        "/e/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    return r.headers["mcp-session-id"]


async def _save_token(engine, redis, provider, server_id, user_id, tokens):
    c = token_cipher(EnvSettings(_env_file=None, token_encryption_keys=[KEY]))
    units = SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis)
    store = UpstreamTokenService(units, c, ValkeyRefreshLock(redis), provider)
    await store.save(server_id, user_id, tokens)


async def test_shared_bearer_attached(engine: AsyncEngine, redis):
    """UPO-2: shared token attached as Bearer to the upstream call."""
    srv = await _seed(engine)
    factory = BearerCapturingFactory()
    provider = FakeUpstreamProvider()
    await _save_token(
        engine,
        redis,
        provider,
        srv.id,
        None,
        UpstreamTokens(access_token="tok-shared", expires_in=3600),
    )
    async with _running(engine, redis, factory, provider) as http:
        session = await _init(http)
        resp = await _call(http, session)
        assert resp.json()["result"]["content"][0]["text"] == "up:x"
    assert factory.seen == ["Bearer tok-shared"]


async def test_missing_token_returns_connect_error(engine, redis):
    """UPO-3: no token -> structured connect-URL error, upstream never called."""
    await _seed(engine)
    factory = BearerCapturingFactory()
    async with _running(engine, redis, factory, FakeUpstreamProvider()) as http:
        session = await _init(http)
        resp = await _call(http, session)
    body = resp.json()
    assert "connect at" in body["error"]["message"]
    assert "/oauth/upstream/up/connect" in body["error"]["message"]
    assert factory.seen == []  # upstream not called


async def test_near_expiry_refreshes_then_attaches(engine, redis):
    """UPO-4: proactive refresh before the call; refreshed bearer attached."""
    srv = await _seed(engine)
    factory = BearerCapturingFactory()
    provider = FakeUpstreamProvider()
    await _save_token(
        engine,
        redis,
        provider,
        srv.id,
        None,
        UpstreamTokens(access_token="stale", refresh_token="rt", expires_in=5),
    )
    async with _running(engine, redis, factory, provider) as http:
        session = await _init(http)
        resp = await _call(http, session)
        assert resp.status_code == 200
    assert provider.refresh_calls == 1
    assert factory.seen == ["Bearer at-refreshed"]


async def test_reactive_retry_on_upstream_error(engine, redis):
    """UPO-4: a 401 despite a fresh token forces a refresh and one retry."""
    srv = await _seed(engine)
    factory = BearerCapturingFactory(reject={"Bearer stale"})  # first bearer rejected
    provider = FakeUpstreamProvider()
    await _save_token(
        engine,
        redis,
        provider,
        srv.id,
        None,
        UpstreamTokens(access_token="stale", refresh_token="rt", expires_in=3600),
    )
    async with _running(engine, redis, factory, provider) as http:
        session = await _init(http)
        resp = await _call(http, session)
        assert resp.json()["result"]["content"][0]["text"] == "up:x"
    # first attempt with the stale (rejected) bearer, retry with the refreshed one
    assert factory.seen == ["Bearer stale", "Bearer at-refreshed"]
    assert provider.refresh_calls == 1


async def test_no_encryption_keys_errors(engine, redis):
    """Without encryption keys, an upstream_oauth call errors instead of storing plaintext."""
    await _seed(engine)
    async with _running(
        engine, redis, BearerCapturingFactory(), FakeUpstreamProvider(), keys=()
    ) as http:
        session = await _init(http)
        resp = await _call(http, session)
    assert "not configured" in resp.json()["error"]["message"]
