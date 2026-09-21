"""Upstream OAuth client tests (spec 23: UPO-1/2/4/5) with an injected provider."""

import asyncio
import json

import pytest
from bundlemcp.application.upstream_oauth.upstream_token_service import UpstreamTokenService
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect
from bundlemcp.domain.upstream_oauth.upstream_metadata import UpstreamMetadata
from bundlemcp.domain.upstream_oauth.upstream_tokens import UpstreamTokens
from bundlemcp.infrastructure.crypto.token_cipher import TokenCipher
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.upstream_oauth_client_row import UpstreamOAuthClientRow
from bundlemcp.infrastructure.postgres.rows.upstream_oauth_token_row import UpstreamOAuthTokenRow
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory
from bundlemcp.infrastructure.valkey.refresh_lock import ValkeyRefreshLock
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select


def cipher() -> TokenCipher:
    return TokenCipher([Fernet.generate_key().decode()])


class FakeProvider:
    """Injected upstream IdP; counts refreshes to prove single-flight."""

    def __init__(self):
        self.refresh_calls = 0
        self.fail_refresh = False

    async def discover(self, server_url):
        return UpstreamMetadata(
            authorization_endpoint="https://idp/authorize",
            token_endpoint="https://idp/token",
        )

    async def register(self, meta, *, redirect_uri, client_name):
        raise AssertionError("a client is already stored")

    def authorize_url(self, meta, **kw):
        return f"{meta.authorization_endpoint}?state={kw['state']}"

    async def exchange(self, meta, **kw):
        return UpstreamTokens(access_token="at-new", refresh_token="rt-new", expires_in=3600)

    async def refresh(self, meta, *, refresh_token, client_id, client_secret):
        self.refresh_calls += 1
        await asyncio.sleep(0.05)
        if self.fail_refresh:
            raise RuntimeError("refresh denied")
        return UpstreamTokens(access_token="at-refreshed", refresh_token="rt-2", expires_in=3600)


async def _seed_server(engine, c, *, with_client=True) -> McpServerRow:
    async with session_factory(engine)() as db:
        srv = McpServerRow(
            name="linear", url="https://linear/mcp", auth_mode=ServerAuthMode.UPSTREAM_OAUTH
        )
        db.add(srv)
        await db.commit()
        await db.refresh(srv)
        if with_client:
            db.add(
                UpstreamOAuthClientRow(
                    server_id=srv.id,
                    client_id="cli-1",
                    client_secret_encrypted=c.encrypt("shh"),
                )
            )
            await db.commit()
        return srv


def _store(engine, redis, provider, c) -> UpstreamTokenService:
    units = SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis)
    return UpstreamTokenService(units, c, ValkeyRefreshLock(redis), provider)


async def test_token_encrypted_at_rest(engine: AsyncEngine, redis):
    """UPO-5/DOM-3: the stored blob is ciphertext, not the token."""
    c = cipher()
    srv = await _seed_server(engine, c)
    store = _store(engine, redis, FakeProvider(), c)
    await store.save(srv.id, None, UpstreamTokens(access_token="secret-at", expires_in=3600))

    async with session_factory(engine)() as db:
        row = (await db.execute(select(UpstreamOAuthTokenRow))).scalar_one()
    assert "secret-at" not in row.tokens_encrypted  # not plaintext
    assert json.loads(c.decrypt(row.tokens_encrypted))["access_token"] == "secret-at"


async def test_fresh_token_returned_without_refresh(engine, redis):
    c = cipher()
    srv = await _seed_server(engine, c)
    provider = FakeProvider()
    store = _store(engine, redis, provider, c)
    await store.save(
        srv.id, None, UpstreamTokens(access_token="at", refresh_token="rt", expires_in=3600)
    )

    assert await store.ensure_access_token(srv, None) == "at"
    assert provider.refresh_calls == 0


async def test_near_expiry_triggers_refresh(engine, redis):
    """UPO-4: proactive refresh when within the skew window."""
    c = cipher()
    srv = await _seed_server(engine, c)
    provider = FakeProvider()
    store = _store(engine, redis, provider, c)
    # expires in 10s -> inside the 60s skew -> refresh
    await store.save(
        srv.id, None, UpstreamTokens(access_token="old", refresh_token="rt", expires_in=10)
    )

    assert await store.ensure_access_token(srv, None) == "at-refreshed"
    assert provider.refresh_calls == 1


async def test_single_flight_refresh(engine, redis):
    """UPO-4: concurrent callers cause exactly one refresh."""
    c = cipher()
    srv = await _seed_server(engine, c)
    provider = FakeProvider()
    store = _store(engine, redis, provider, c)
    await store.save(
        srv.id, None, UpstreamTokens(access_token="old", refresh_token="rt", expires_in=5)
    )

    results = await asyncio.gather(
        store.ensure_access_token(srv, None),
        store.ensure_access_token(srv, None),
        store.ensure_access_token(srv, None),
    )
    assert all(r == "at-refreshed" for r in results)
    assert provider.refresh_calls == 1  # single-flight


async def test_refresh_failure_invalidates_and_raises(engine, redis):
    c = cipher()
    srv = await _seed_server(engine, c)
    provider = FakeProvider()
    provider.fail_refresh = True
    store = _store(engine, redis, provider, c)
    await store.save(
        srv.id, None, UpstreamTokens(access_token="old", refresh_token="rt", expires_in=5)
    )

    with pytest.raises(NeedsConnect):
        await store.ensure_access_token(srv, None)
    async with session_factory(engine)() as db:
        row = (await db.execute(select(UpstreamOAuthTokenRow))).scalar_one()
    assert row.is_valid is False


async def test_missing_token_raises_needs_connect(engine, redis):
    c = cipher()
    srv = await _seed_server(engine, c)
    store = _store(engine, redis, FakeProvider(), c)
    with pytest.raises(NeedsConnect):
        await store.ensure_access_token(srv, None)


async def test_per_user_isolation(engine, redis):
    """UPO-2: (server, userA) and (server, userB) tokens are independent."""
    c = cipher()
    srv = await _seed_server(engine, c)
    store = _store(engine, redis, FakeProvider(), c)
    # users must exist for the FK; use NULL-user shared + one real user
    from bundlemcp.infrastructure.postgres.rows.user_row import UserRow

    async with session_factory(engine)() as db:
        ua = UserRow(oidc_issuer="i", oidc_sub="a")
        db.add(ua)
        await db.commit()
        await db.refresh(ua)
    await store.save(srv.id, ua.id, UpstreamTokens(access_token="at-a", expires_in=3600))
    await store.save(srv.id, None, UpstreamTokens(access_token="at-shared", expires_in=3600))

    assert await store.ensure_access_token(srv, ua.id) == "at-a"
    assert await store.ensure_access_token(srv, None) == "at-shared"


async def test_status_hides_token_values(engine, redis):
    """UPO-5: status returns connection state only."""
    c = cipher()
    srv = await _seed_server(engine, c)
    store = _store(engine, redis, FakeProvider(), c)
    await store.save(
        srv.id, None, UpstreamTokens(access_token="secret", expires_in=3600, account_hint="a@b.com")
    )
    status = await store.status(srv.id, None)
    assert status.connected is True
    assert status.account_hint == "a@b.com"
    assert "secret" not in status.model_dump_json()
