"""The startup warning about static headers stored in plaintext (ARC-18, SEC-10)."""

import pytest
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.infrastructure.crypto.token_cipher import TokenCipher
from bundlemcp.infrastructure.postgres.engine import session_factory
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWorkFactory
from cryptography.fernet import Fernet
from structlog.testing import capture_logs

from tests.conftest import hermetic_settings, serving
from tests.redaction import assert_redacted

HEADERS = {"X-Api-Key": "k3y-value", "Authorization": "Bearer s3cret"}


async def _store(engine, redis, cipher=None) -> None:
    units = SqlAlchemyUnitOfWorkFactory(session_factory(engine), redis, cipher=cipher)
    async with units.open() as uow:
        for name in ("one", "two"):
            url = f"https://{name}.example/mcp"
            uow.servers.add(McpServer(name=name, url=url, static_headers=HEADERS))
        uow.servers.add(McpServer(name="bare", url="https://bare.example/mcp"))
        await uow.commit()


@pytest.fixture(autouse=True)
def _keep_structlog_capture(monkeypatch):
    """Building the app reconfigures structlog, which would end capture_logs before startup."""
    monkeypatch.setattr("bundlemcp.main.app.configure_logging", lambda *args, **kwargs: None)


def _warnings(logs: list[dict]) -> list[dict]:
    return [entry for entry in logs if entry["event"] == "static_headers.plaintext"]


async def test_arc18_keyless_startup_warns_with_count_only(engine, redis):
    """ARC-18/SEC-10: a keyless gateway with two plaintext header sets warns once at startup,
    naming the count and the reason, and no header name, value or server name."""
    await _store(engine, redis)
    with capture_logs() as logs:
        async with serving(engine, redis, settings=hermetic_settings()):
            pass
    [warning] = _warnings(logs)
    assert warning["log_level"] == "warning"
    assert warning["servers"] == 2
    assert warning["reason"] == "no_encryption_key"
    secrets = [*HEADERS, *HEADERS.values(), "s3cret", "one", "two"]
    assert_redacted(repr(warning), secrets)


async def test_arc18_keyed_startup_warns_until_the_pass_seals(engine, redis):
    """ARC-18: with a key but rows not yet sealed, the warning names the pending pass."""
    await _store(engine, redis)
    settings = hermetic_settings(token_encryption_keys=[Fernet.generate_key().decode()])
    with capture_logs() as logs:
        async with serving(engine, redis, settings=settings):
            pass
    [warning] = _warnings(logs)
    assert warning["servers"] == 2
    assert warning["reason"] == "awaiting_reencryption_pass"


async def test_arc18_no_warning_when_nothing_plaintext(engine, redis):
    """ARC-18: a gateway whose headers are all encrypted logs no plaintext warning."""
    key = Fernet.generate_key().decode()
    await _store(engine, redis, TokenCipher([key]))
    with capture_logs() as logs:
        async with serving(engine, redis, settings=hermetic_settings(token_encryption_keys=[key])):
            pass
    assert _warnings(logs) == []
