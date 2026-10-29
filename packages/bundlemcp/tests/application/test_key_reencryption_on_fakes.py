"""Stored secrets move to the primary key when they are read (DEP-9)."""

import json
import uuid

import pytest
from bundlemcp.application.upstream_oauth.upstream_token_storage import UpstreamTokenStorage
from bundlemcp.domain.shared.system_clock import SystemClock
from bundlemcp.domain.upstream_oauth.upstream_oauth_client import UpstreamOAuthClient
from bundlemcp.domain.upstream_oauth.upstream_tokens import UpstreamTokens
from bundlemcp.infrastructure.config.structured_logging import configure_logging
from bundlemcp.infrastructure.crypto.token_cipher import TokenCipher
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
    InMemoryUnitOfWorkFactory,
)
from cryptography.fernet import Fernet

from tests.redaction import assert_redacted

SERVER = uuid.uuid4()


def key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def keys() -> tuple[str, str]:
    return key(), key()  # old, new


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


async def stored_under(uow, cipher: TokenCipher, access_token: str = "at") -> None:
    storage = UpstreamTokenStorage(InMemoryUnitOfWorkFactory(uow), cipher, clock=SystemClock())
    await storage.save(SERVER, None, UpstreamTokens(access_token=access_token, expires_in=3600))


async def test_dep9_reading_an_old_token_leaves_it_under_the_new_key(uow, keys):
    """DEP-9: the read succeeds and the stored value is afterwards current."""
    old, new = keys
    await stored_under(uow, TokenCipher([old]))
    rotated = TokenCipher([new, old])
    storage = UpstreamTokenStorage(InMemoryUnitOfWorkFactory(uow), rotated, clock=SystemClock())

    row = await storage.load(SERVER, None)
    assert storage.decode(row).access_token == "at"
    stored = (await uow.upstream_tokens.find(SERVER, None)).tokens_encrypted
    assert rotated.is_current(stored)
    assert TokenCipher([new]).decrypt(stored)  # the old key is no longer needed


async def test_dep9_reading_an_old_client_secret_moves_it_too(uow, keys):
    old, new = keys
    uow.upstream_clients.add(
        UpstreamOAuthClient(
            server_id=SERVER,
            client_id="cid",
            client_secret_encrypted=TokenCipher([old]).encrypt("secret"),
        )
    )
    rotated = TokenCipher([new, old])
    config = await UpstreamTokenStorage(
        InMemoryUnitOfWorkFactory(uow), rotated, clock=SystemClock()
    ).client_config(SERVER)
    assert config.client_secret == "secret"
    stored = (await uow.upstream_clients.for_server(SERVER)).client_secret_encrypted
    assert rotated.is_current(stored)


async def test_dep9_a_failing_write_does_not_fail_the_read(uow, keys, monkeypatch):
    """DEP-9: re-encryption is best effort; the call in progress keeps its plaintext."""
    old, new = keys
    await stored_under(uow, TokenCipher([old]))

    async def broken(*args, **kwargs):
        raise ConnectionError("database went away")

    monkeypatch.setattr(uow.upstream_tokens, "replace_ciphertext", broken)
    storage = UpstreamTokenStorage(
        InMemoryUnitOfWorkFactory(uow), TokenCipher([new, old]), clock=SystemClock()
    )
    row = await storage.load(SERVER, None)
    assert storage.decode(row).access_token == "at"


async def test_dep9_a_refresh_that_lands_first_is_never_overwritten(uow, keys, monkeypatch):
    """DEP-9: the conditional write loses to a concurrent refresh, whose tokens survive."""
    old, new = keys
    await stored_under(uow, TokenCipher([old]), access_token="before")
    rotated = TokenCipher([new, old])
    storage = UpstreamTokenStorage(InMemoryUnitOfWorkFactory(uow), rotated, clock=SystemClock())
    original = uow.upstream_tokens.replace_ciphertext

    async def refresh_first(row_id, expected, new_value):
        # a refresh stores new tokens between this read and its re-encryption
        await storage.save(SERVER, None, UpstreamTokens(access_token="refreshed", expires_in=60))
        return await original(row_id, expected, new_value)

    monkeypatch.setattr(uow.upstream_tokens, "replace_ciphertext", refresh_first)
    await storage.load(SERVER, None)
    stored = (await uow.upstream_tokens.find(SERVER, None)).tokens_encrypted
    assert UpstreamTokens.model_validate_json(rotated.decrypt(stored)).access_token == "refreshed"


async def test_dep9_the_sweep_moves_what_nobody_reads_and_counts_the_rest(uow, keys):
    """DEP-9: rewritten, remaining-on-old-key and undecryptable are reported separately."""
    from bundlemcp.application.upstream_oauth.secret_reencryption import (
        BATCH_SIZE,
        SecretReencryption,
    )

    old, new = keys
    old_cipher, rotated = TokenCipher([old]), TokenCipher([new, old])
    for _ in range(BATCH_SIZE + 3):  # more than one batch
        await UpstreamTokenStorage(
            InMemoryUnitOfWorkFactory(uow), old_cipher, clock=SystemClock()
        ).save(uuid.uuid4(), None, UpstreamTokens(access_token="at", expires_in=60))
    uow.upstream_clients.add(
        UpstreamOAuthClient(server_id=SERVER, client_secret_encrypted=old_cipher.encrypt("s"))
    )
    uow.upstream_clients.add(
        UpstreamOAuthClient(server_id=uuid.uuid4(), client_secret_encrypted=rotated.encrypt("ok"))
    )
    stranger = TokenCipher([key()]).encrypt("lost")
    uow.upstream_clients.add(
        UpstreamOAuthClient(server_id=uuid.uuid4(), client_secret_encrypted=stranger)
    )
    sweeper = SecretReencryption(InMemoryUnitOfWorkFactory(uow), rotated)

    first = await sweeper.sweep()
    assert (first.rewritten, first.remaining_on_old_key, first.undecryptable) == (
        BATCH_SIZE + 4,
        0,
        1,
    )
    secret = (await uow.upstream_clients.for_server(SERVER)).client_secret_encrypted
    assert TokenCipher([new]).decrypt(secret) == "s"  # safe to drop the old key

    again = await sweeper.sweep()
    assert (again.rewritten, again.remaining_on_old_key, again.undecryptable) == (0, 0, 1)


async def test_dep9_a_failing_write_is_counted_as_still_on_the_old_key(uow, keys, monkeypatch):
    from bundlemcp.application.upstream_oauth.secret_reencryption import SecretReencryption

    old, new = keys
    await stored_under(uow, TokenCipher([old]))

    async def broken(*args, **kwargs):
        raise ConnectionError("database went away")

    monkeypatch.setattr(uow.upstream_tokens, "replace_ciphertext", broken)
    sweep = await SecretReencryption(
        InMemoryUnitOfWorkFactory(uow), TokenCipher([new, old])
    ).sweep()
    assert sweep.remaining_on_old_key == 1 and sweep.rewritten == 0


@pytest.mark.parametrize("log_format", ["json", "text"])
async def test_dep9_failed_reencryption_logs_its_cause(uow, keys, monkeypatch, capsys, log_format):
    """DEP-9, OPS-8: a failed rewrite is logged with the exception that caused it, and the line
    carries neither the old nor the new ciphertext, though both were in the failing frame."""
    old, new = keys
    await stored_under(uow, TokenCipher([old]))
    seen: list[str] = []

    async def broken(row_id, stored, rewritten):
        seen.extend([stored, rewritten])
        raise ConnectionError("database went away")

    monkeypatch.setattr(uow.upstream_tokens, "replace_ciphertext", broken)
    storage = UpstreamTokenStorage(
        InMemoryUnitOfWorkFactory(uow), TokenCipher([new, old]), clock=SystemClock()
    )
    configure_logging("INFO", log_format)
    await storage.load(SERVER, None)
    out = capsys.readouterr().err
    assert "token_encryption.reencrypt_failed" in out
    assert "ConnectionError: database went away" in out
    if log_format == "json":
        (line,) = [json.loads(raw) for raw in out.splitlines() if "reencrypt_failed" in raw]
        assert "Traceback (most recent call last):" in line["exception"]
    assert len(seen) == 2
    assert_redacted(out, seen)
