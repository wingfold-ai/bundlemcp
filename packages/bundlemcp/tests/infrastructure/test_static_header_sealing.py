"""Sealing plaintext static headers and moving them to a new key (DEP-9, ARC-18)."""

import json

import pytest
from bundlemcp.application.upstream_oauth.secret_reencryption import SecretReencryption
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.infrastructure.crypto.token_cipher import TokenCipher
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory
from cryptography.fernet import Fernet
from sqlalchemy import text

HEADERS = {"Authorization": "Bearer s3cret"}


def key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def keys() -> tuple[str, str]:
    return key(), key()  # old, new


def units(engine, redis, cipher=None) -> SqlAlchemyUnitOfWorkFactory:
    return SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis, cipher=cipher)


async def store(factory, *servers: McpServer) -> None:
    async with factory.open() as uow:
        for server in servers:
            uow.servers.add(server)
        await uow.commit()


async def stored(engine, server: McpServer) -> tuple[dict, str | None]:
    async with engine.connect() as conn:
        plaintext, ciphertext = (
            await conn.execute(
                text(
                    "SELECT static_headers, static_headers_encrypted FROM mcp_servers "
                    "WHERE id = :id"
                ),
                {"id": server.id.hex},
            )
        ).one()
    return json.loads(plaintext), ciphertext


def server(name: str, headers: dict[str, str] | None = None) -> McpServer:
    return McpServer(name=name, url=f"https://{name}.example/mcp", static_headers=headers or {})


async def test_dep9_sweep_seals_plaintext_headers(engine, redis, keys):
    """DEP-9/ARC-18: the pass encrypts headers stored before a key was configured, empties the
    plaintext column, and reports them as sealed."""
    _, new = keys
    plain = server("plain", HEADERS)
    bare = server("bare")
    await store(units(engine, redis), plain, bare)
    cipher = TokenCipher([new])
    factory = units(engine, redis, cipher)
    async with factory.open() as uow:
        assert await uow.servers.count_plaintext_headers() == 1

    sweep = await SecretReencryption(factory, cipher).sweep()

    assert sweep.sealed == 1
    plaintext, ciphertext = await stored(engine, plain)
    assert plaintext == {}
    assert json.loads(cipher.decrypt(ciphertext)) == HEADERS
    assert await stored(engine, bare) == ({}, None)
    async with factory.open() as uow:
        assert await uow.servers.count_plaintext_headers() == 0
        assert (await uow.servers.get(plain.id)).static_headers == HEADERS


async def test_dep9_sweep_seals_more_than_one_batch(engine, redis, keys, monkeypatch):
    """DEP-9: sealing continues batch after batch until every plaintext row is sealed."""
    from bundlemcp.application.upstream_oauth import secret_reencryption

    monkeypatch.setattr(secret_reencryption, "BATCH_SIZE", 2)
    servers = [server(f"s{i}", {"x-key": f"v{i}"}) for i in range(5)]
    await store(units(engine, redis), *servers)
    cipher = TokenCipher([keys[1]])
    sweep = await SecretReencryption(units(engine, redis, cipher), cipher).sweep()
    assert sweep.sealed == 5
    for s in servers:
        assert (await stored(engine, s))[0] == {}


async def test_dep9_static_headers_move_to_new_key(engine, redis, keys):
    """DEP-9: headers stored under the old key are rewritten under the new one, still decrypt to
    the same values, and nothing is left on the old key."""
    old, new = keys
    s = server("seo", HEADERS)
    await store(units(engine, redis, TokenCipher([old])), s)
    rotated = TokenCipher([new, old])

    sweep = await SecretReencryption(units(engine, redis, rotated), rotated).sweep()

    assert sweep.rewritten == 1 and sweep.remaining_on_old_key == 0 and sweep.sealed == 0
    _, ciphertext = await stored(engine, s)
    assert json.loads(TokenCipher([new]).decrypt(ciphertext)) == HEADERS


async def test_dep9_undecryptable_static_headers_counted(engine, redis, keys):
    """DEP-9: headers no held key decrypts are left unchanged and counted as undecryptable."""
    old, new = keys
    s = server("seo", HEADERS)
    await store(units(engine, redis, TokenCipher([old])), s)
    before = await stored(engine, s)
    cipher = TokenCipher([new])

    sweep = await SecretReencryption(units(engine, redis, cipher), cipher).sweep()

    assert sweep.undecryptable == 1 and sweep.rewritten == 0
    assert await stored(engine, s) == before


@pytest.mark.parametrize("writer", ["previous_release", "this_release"])
async def test_dep9_seal_skips_row_written_meanwhile(engine, redis, keys, writer):
    """DEP-9: headers an admin writes while the pass is sealing the old ones are kept: a
    plaintext write by a previous-release replica and an encrypted one by this release alike."""
    cipher = TokenCipher([keys[1]])
    s = server("seo", {"Authorization": "Bearer old"})
    await store(units(engine, redis), s)
    admin_ciphertext = cipher.encrypt(json.dumps({"Authorization": "Bearer new"}))

    async with units(engine, redis, cipher).open() as uow:
        repository = uow.servers
        seal = repository._seal

        async def admin_writes_first(cipher, server_id, stored_text):
            if writer == "previous_release":
                statement = "UPDATE mcp_servers SET static_headers = :h WHERE id = :id"
                values = {"h": json.dumps({"Authorization": "Bearer new"}), "id": s.id.hex}
            else:
                statement = (
                    "UPDATE mcp_servers SET static_headers = '{}', "
                    "static_headers_encrypted = :c WHERE id = :id"
                )
                values = {"c": admin_ciphertext, "id": s.id.hex}
            await uow.session.execute(text(statement), values)
            return await seal(cipher, server_id, stored_text)

        repository._seal = admin_writes_first
        assert await repository.seal_plaintext_headers(10) == 0
        await uow.commit()

    async with units(engine, redis, cipher).open() as uow:
        assert (await uow.servers.get(s.id)).static_headers == {"Authorization": "Bearer new"}
