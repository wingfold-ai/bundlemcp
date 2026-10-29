"""Static header values encrypted at rest by the server repository (ARC-18, SEC-10)."""

import json

import pytest
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.infrastructure.crypto.token_cipher import TokenCipher
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory
from cryptography.fernet import Fernet
from sqlalchemy import text
from structlog.testing import capture_logs

HEADERS = {"Authorization": "Bearer s3cret"}


def key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def cipher() -> TokenCipher:
    return TokenCipher([key()])


def units(engine, redis, cipher=None) -> SqlAlchemyUnitOfWorkFactory:
    return SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis, cipher=cipher)


async def raw_row(engine, server: McpServer) -> dict:
    """The mcp_servers row as stored, every column as text."""
    async with engine.connect() as conn:
        row = (
            (
                await conn.execute(
                    text("SELECT * FROM mcp_servers WHERE id = :id"), {"id": server.id.hex}
                )
            )
            .mappings()
            .one()
        )
    return dict(row)


async def store(factory: SqlAlchemyUnitOfWorkFactory, server: McpServer) -> None:
    async with factory.open() as uow:
        uow.servers.add(server)
        await uow.commit()


async def read(factory: SqlAlchemyUnitOfWorkFactory, server: McpServer) -> McpServer:
    async with factory.open() as uow:
        found = await uow.servers.get(server.id)
    assert found is not None
    return found


async def test_arc18_static_headers_stored_encrypted(engine, redis, cipher):
    """ARC-18: with a cipher the plaintext column holds nothing, the ciphertext column decrypts
    to the headers, and the entity reads back equal."""
    factory = units(engine, redis, cipher)
    server = McpServer(name="seo", url="https://seo.example/mcp", static_headers=HEADERS)
    await store(factory, server)

    row = await raw_row(engine, server)
    assert json.loads(row["static_headers"]) == {}
    assert json.loads(cipher.decrypt(row["static_headers_encrypted"])) == HEADERS
    assert (await read(factory, server)).static_headers == HEADERS


async def test_arc18_without_cipher_stores_plaintext(engine, redis):
    """ARC-18: a keyless gateway stores and reads the plaintext column as before."""
    factory = units(engine, redis)
    server = McpServer(name="seo", url="https://seo.example/mcp", static_headers=HEADERS)
    await store(factory, server)

    row = await raw_row(engine, server)
    assert json.loads(row["static_headers"]) == HEADERS
    assert row["static_headers_encrypted"] is None
    assert (await read(factory, server)).static_headers == HEADERS


async def test_arc18_plaintext_row_read_with_cipher(engine, redis, cipher):
    """ARC-18: a row written before a key was configured is read from its plaintext column, and
    the next write of the server encrypts it."""
    server = McpServer(name="seo", url="https://seo.example/mcp", static_headers=HEADERS)
    await store(units(engine, redis), server)

    factory = units(engine, redis, cipher)
    found = await read(factory, server)
    assert found.static_headers == HEADERS
    found.description = "edited"
    await store(factory, found)
    row = await raw_row(engine, server)
    assert json.loads(row["static_headers"]) == {}
    assert json.loads(cipher.decrypt(row["static_headers_encrypted"])) == HEADERS


@pytest.mark.parametrize("held", ["other_key", "no_key"])
async def test_arc18_undecryptable_headers_kept_on_unrelated_write(engine, redis, cipher, held):
    """ARC-18: headers no held key decrypts read as none, are logged by server id only, and
    survive an edit of the server's description unchanged."""
    server = McpServer(name="seo", url="https://seo.example/mcp", static_headers=HEADERS)
    await store(units(engine, redis, cipher), server)
    stored = (await raw_row(engine, server))["static_headers_encrypted"]

    factory = units(engine, redis, TokenCipher([key()]) if held == "other_key" else None)
    with capture_logs() as logs:
        async with factory.open() as uow:
            found = await uow.servers.get(server.id)
            assert found is not None and found.static_headers == {}
            found.description = "edited"
            uow.servers.add(found)
            await uow.commit()
    row = await raw_row(engine, server)
    assert row["static_headers_encrypted"] == stored
    assert row["description"] == "edited"
    assert any(e["event"] == "server.static_headers_undecryptable" for e in logs)
    assert "s3cret" not in repr(logs) and "Authorization" not in repr(logs)
    assert (await read(units(engine, redis, cipher), server)).static_headers == HEADERS


async def test_arc18_new_headers_replace_undecryptable_ones(engine, redis, cipher):
    """ARC-18: an admin writing new headers replaces a ciphertext no held key decrypts."""
    server = McpServer(name="seo", url="https://seo.example/mcp", static_headers=HEADERS)
    await store(units(engine, redis, TokenCipher([key()])), server)

    factory = units(engine, redis, cipher)
    async with factory.open() as uow:
        found = await uow.servers.get(server.id)
        found.static_headers = {"Authorization": "Bearer new"}
        uow.servers.add(found)
        await uow.commit()
    assert (await read(factory, server)).static_headers == {"Authorization": "Bearer new"}


async def test_sec10_static_header_values_are_ciphertext_in_database(engine, redis, cipher):
    """SEC-10: with a key, no column of the stored server row carries the header value."""
    factory = units(engine, redis, cipher)
    server = McpServer(name="seo", url="https://seo.example/mcp", static_headers=HEADERS)
    await store(factory, server)
    row = await raw_row(engine, server)
    for value in row.values():
        assert "s3cret" not in str(value)
        assert "Bearer s3cret" not in str(value)
