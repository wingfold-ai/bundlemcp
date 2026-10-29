"""Every shape of upstream OAuth client metadata the gateway has stored, read back from rows."""

from typing import Any

import pytest
from bundlemcp.application.management.upstream_oauth_config_service import (
    UpstreamOAuthConfigService,
)
from bundlemcp.application.schemas import UpstreamOAuthConfig
from bundlemcp.application.upstream_oauth.upstream_token_storage import UpstreamTokenStorage
from bundlemcp.domain.shared.system_clock import SystemClock
from bundlemcp.domain.upstream_oauth.client_identification import ClientIdentification
from bundlemcp.domain.upstream_oauth.upstream_client_registration import (
    UpstreamClientRegistration,
)
from bundlemcp.domain.upstream_oauth.upstream_grant import UpstreamGrant
from bundlemcp.domain.upstream_oauth.upstream_metadata import UpstreamMetadata
from bundlemcp.infrastructure.crypto.token_cipher import TokenCipher
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.upstream_oauth_client_row import (
    UpstreamOAuthClientRow,
)
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory
from cryptography.fernet import Fernet
from sqlmodel import select

DISCOVERED = UpstreamMetadata(
    authorization_endpoint="https://as.example/authorize",
    token_endpoint="https://as.example/token",
    registration_endpoint="https://as.example/register",
    scopes_supported=["read", "write"],
    resource_scopes=["read"],
    issuer="https://as.example",
    authorization_response_iss_parameter_supported=True,
    resource="https://mcp.example/mcp",
)
ADMIN = {
    "authorization_endpoint": "https://idp.example/auth",
    "token_endpoint": "https://idp.example/token",
    "identification": "preregistered",
    "grant_type": "client_credentials",
}
GATEWAY = {
    **DISCOVERED.model_dump(exclude_none=True, exclude={"step_up_scopes"}),
    "identification": "dynamic_registration",
}
BEFORE_IDENTIFICATION = DISCOVERED.model_dump(exclude_none=True)
STEPPED_UP = {**GATEWAY, "step_up_scopes": ["admin", "audit"]}
UNKNOWN_KEY = {**ADMIN, "grant_type": "authorization_code", "x-note": "kept"}


@pytest.fixture
def units(engine, redis) -> SqlAlchemyUnitOfWorkFactory:
    return SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis)


async def _store(engine, metadata: dict[str, Any], *, client_id: str | None = "cid"):
    async with session_factory(engine)() as db:
        server = McpServerRow(name="up", url="https://mcp.example/mcp")
        db.add(server)
        await db.flush()
        db.add(UpstreamOAuthClientRow(server_id=server.id, client_id=client_id, metadata_=metadata))
        await db.commit()
        return server.id


async def _stored_metadata(engine) -> dict[str, Any]:
    async with session_factory(engine)() as db:
        return (await db.execute(select(UpstreamOAuthClientRow))).scalar_one().metadata_


async def _resave(units, server_id) -> None:
    """Read the client through the repository and write it back unchanged."""
    async with units.open() as uow:
        client = await uow.upstream_clients.for_server(server_id)
        assert client is not None
        uow.upstream_clients.add(client)
        await uow.commit()


def _storage(units) -> UpstreamTokenStorage:
    return UpstreamTokenStorage(
        units, TokenCipher([Fernet.generate_key().decode()]), clock=SystemClock()
    )


@pytest.mark.parametrize(
    ("stored", "identification", "grant", "issuer", "step_up", "admin_stored"),
    [
        (ADMIN, "preregistered", "client_credentials", None, [], True),
        (GATEWAY, "dynamic_registration", "authorization_code", "https://as.example", [], False),
        (
            BEFORE_IDENTIFICATION,
            "preregistered",
            "authorization_code",
            "https://as.example",
            [],
            True,
        ),
        (
            STEPPED_UP,
            "dynamic_registration",
            "authorization_code",
            "https://as.example",
            ["admin", "audit"],
            False,
        ),
        ({}, "preregistered", "authorization_code", None, [], True),
        (UNKNOWN_KEY, "preregistered", "authorization_code", None, [], True),
    ],
    ids=["admin", "gateway", "before-identification", "step-up", "forgotten", "unknown-key"],
)
async def test_ups25_ups34_ups35_every_stored_shape_reads_the_same(
    engine, units, stored, identification, grant, issuer, step_up, admin_stored
):
    """UPS-25, UPS-34, UPS-35: each metadata shape ever stored reads as the same client, and
    writing the client back leaves the stored JSON as it was."""
    server_id = await _store(engine, stored)

    config = await _storage(units).find_client_config(server_id)

    assert config is not None
    assert config.identification == ClientIdentification(identification)
    assert config.grant == UpstreamGrant(grant)
    assert config.issuer == issuer
    assert config.step_up_scopes == step_up
    assert config.is_admin_stored is admin_stored
    await _resave(units, server_id)
    assert await _stored_metadata(engine) == stored


async def test_ups25_a_forgotten_registration_has_no_client(engine, units):
    """UPS-25: once forgotten, a server has no client config and keeps an empty record."""
    server_id = await _store(engine, {}, client_id=None)

    assert await _storage(units).find_client_config(server_id) is None
    await _resave(units, server_id)
    assert await _stored_metadata(engine) == {}


class _NoConnections:
    configured = False

    async def status(self, server_id, user_id):
        return None

    async def disconnect(self, server_id, user_id):
        return None

    async def connect_as_client(self, server):
        return None


async def test_ups25_a_registration_is_stored_flat(engine, units):
    """UPS-25: a client the gateway obtained is stored as the discovered endpoints beside how
    it was obtained, replacing whatever the record held."""
    server_id = await _store(engine, {}, client_id=None)

    await _storage(units).save_registration(
        server_id,
        UpstreamClientRegistration(client_id="dyn"),
        DISCOVERED.model_copy(update={"step_up_scopes": ["ignored"]}),
        ClientIdentification.DYNAMIC_REGISTRATION,
    )

    assert await _stored_metadata(engine) == GATEWAY
    assert list(await _stored_metadata(engine)) == list(GATEWAY)


@pytest.mark.parametrize("stored", [GATEWAY, UNKNOWN_KEY], ids=["gateway", "unknown-key"])
async def test_ups34_step_up_scopes_are_appended_in_order(engine, units, stored):
    """UPS-34: demanded scopes are added once each, in order, and nothing else changes."""
    server_id = await _store(engine, stored)
    storage = _storage(units)

    assert await storage.add_step_up_scopes(server_id, ["audit", "admin"]) is True
    assert await storage.add_step_up_scopes(server_id, ["admin", "export"]) is True
    assert await storage.add_step_up_scopes(server_id, ["audit"]) is False

    assert await _stored_metadata(engine) == {
        **stored,
        "step_up_scopes": ["audit", "admin", "export"],
    }


@pytest.mark.parametrize(
    ("stored", "urls", "expected"),
    [
        (
            {},
            True,
            {
                "authorization_endpoint": "https://idp.example/a",
                "token_endpoint": "https://idp.example/t",
                "identification": "preregistered",
                "grant_type": "authorization_code",
            },
        ),
        (
            STEPPED_UP,
            True,
            {
                **STEPPED_UP,
                "authorization_endpoint": "https://idp.example/a",
                "token_endpoint": "https://idp.example/t",
                "identification": "preregistered",
                "grant_type": "authorization_code",
            },
        ),
        (
            STEPPED_UP,
            False,
            {**STEPPED_UP, "identification": "preregistered", "grant_type": "authorization_code"},
        ),
        (UNKNOWN_KEY, False, UNKNOWN_KEY),
    ],
    ids=["new", "over-gateway-with-urls", "over-gateway-without-urls", "unknown-key"],
)
async def test_ups35_an_admin_client_keeps_what_it_does_not_replace(
    engine, units, stored, urls, expected
):
    """UPS-35: storing a client as an admin marks it preregistered with its grant, replaces the
    two URLs only when both are given, and keeps every other remembered key."""
    await _store(engine, stored, client_id="old")
    async with units.open() as uow:
        await UpstreamOAuthConfigService(
            uow, cipher=TokenCipher([Fernet.generate_key().decode()]), connections=_NoConnections()
        ).set_client(
            "up",
            UpstreamOAuthConfig(
                client_id="admin",
                authorization_url="https://idp.example/a" if urls else None,
                token_url="https://idp.example/t" if urls else None,
            ),
        )

    assert await _stored_metadata(engine) == expected
