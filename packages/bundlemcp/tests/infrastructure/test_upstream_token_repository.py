"""Upstream OAuth connections in the durable store (AUTH-20)."""

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
