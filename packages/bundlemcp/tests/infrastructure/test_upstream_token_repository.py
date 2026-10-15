"""Upstream OAuth connections and client secrets in the durable store (AUTH-20, DEP-9)."""

from bundlemcp.domain.access.user import User
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.upstream_oauth.upstream_oauth_token import UpstreamOAuthToken
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory


async def test_auth20_deleting_a_users_upstream_tokens_spares_everyone_else(engine, redis):
    """AUTH-20: only the user's own connections go; the shared one and other users' stay."""
    units = SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis)
    server = McpServer(name="seo", url="https://seo.example/mcp")
    leaving = User(oidc_issuer="i", oidc_sub="a")
    staying = User(oidc_issuer="i", oidc_sub="b")
    async with units.open() as uow:
        uow.servers.add(server)
        uow.users.add(leaving)
        uow.users.add(staying)
        await uow.commit()
        for owner in (leaving.id, staying.id, None):
            uow.upstream_tokens.add(
                UpstreamOAuthToken(server_id=server.id, user_id=owner, tokens_encrypted="x")
            )
        await uow.commit()

    async with units.open() as uow:
        assert await uow.upstream_tokens.delete_for_user(leaving.id) == 1
        await uow.commit()

    async with units.open() as uow:
        owners = {t.user_id for t in await uow.upstream_tokens.for_server(server.id)}
    assert owners == {staying.id, None}


async def test_dep9_replace_ciphertext_only_when_the_value_is_unchanged(engine, redis):
    """DEP-9: a stale expected value changes nothing and reports false, for tokens and secrets."""
    from bundlemcp.domain.upstream_oauth.upstream_oauth_client import UpstreamOAuthClient

    units = SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis)
    server = McpServer(name="seo", url="https://seo.example/mcp")
    async with units.open() as uow:
        uow.servers.add(server)
        await uow.commit()
        token = UpstreamOAuthToken(server_id=server.id, user_id=None, tokens_encrypted="v1")
        client = UpstreamOAuthClient(server_id=server.id, client_secret_encrypted="s1")
        uow.upstream_tokens.add(token)
        uow.upstream_clients.add(client)
        await uow.commit()

    async with units.open() as uow:
        assert await uow.upstream_tokens.replace_ciphertext(token.id, "stale", "v2") is False
        assert await uow.upstream_clients.replace_ciphertext(client.id, "stale", "s2") is False
        assert await uow.upstream_tokens.replace_ciphertext(token.id, "v1", "v2") is True
        assert await uow.upstream_clients.replace_ciphertext(client.id, "s1", "s2") is True
        await uow.commit()

    async with units.open() as uow:
        assert (await uow.upstream_tokens.find(server.id, None)).tokens_encrypted == "v2"
        assert (await uow.upstream_clients.for_server(server.id)).client_secret_encrypted == "s2"


async def test_dep9_the_memory_fakes_replace_ciphertext_the_same_way():
    """DEP-9: the in-memory repositories honour the same compare-and-set."""
    import uuid

    from bundlemcp.domain.upstream_oauth.upstream_oauth_client import UpstreamOAuthClient
    from bundlemcp.infrastructure.memory.in_memory_unit_of_work import InMemoryUnitOfWork

    uow = InMemoryUnitOfWork()
    token = UpstreamOAuthToken(server_id=uuid.uuid4(), user_id=None, tokens_encrypted="v1")
    client = UpstreamOAuthClient(server_id=uuid.uuid4(), client_secret_encrypted="s1")
    uow.upstream_tokens.add(token)
    uow.upstream_clients.add(client)
    assert await uow.upstream_tokens.replace_ciphertext(token.id, "stale", "v2") is False
    assert await uow.upstream_clients.replace_ciphertext(client.id, "stale", "s2") is False
    assert await uow.upstream_tokens.replace_ciphertext(token.id, "v1", "v2") is True
    assert await uow.upstream_clients.replace_ciphertext(client.id, "s1", "s2") is True
    assert token.tokens_encrypted == "v2" and client.client_secret_encrypted == "s2"


async def test_dep9_page_after_walks_every_row_once_in_id_order(engine, redis):
    """DEP-9: the sweep's keyset paging visits every stored connection exactly once."""
    units = SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis)
    servers = [McpServer(name=f"s{i}", url=f"https://s{i}.example/mcp") for i in range(5)]
    async with units.open() as uow:
        for server in servers:
            uow.servers.add(server)
        await uow.commit()
        for server in servers:
            uow.upstream_tokens.add(
                UpstreamOAuthToken(server_id=server.id, user_id=None, tokens_encrypted="x")
            )
        await uow.commit()

    seen, after = [], None
    async with units.open() as uow:
        while page := await uow.upstream_tokens.page_after(after, 2):
            seen.extend(t.id for t in page)
            after = page[-1].id
    assert len(seen) == 5 and seen == sorted(seen) and len(set(seen)) == 5
