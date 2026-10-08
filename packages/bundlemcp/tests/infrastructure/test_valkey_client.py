"""The Valkey client survives a store restart underneath its connection pool (SES-14, #85)."""

import asyncio

import pytest
from bundlemcp.infrastructure.valkey.client import create_redis
from redis.asyncio import Redis
from redis.exceptions import ConnectionError


class RestartingStore:
    """A RESP endpoint that answers PING, and can forget every open connection.

    After ``restart()`` a connection that existed before reads the next command
    and is reset without a reply, as a restarted Valkey behind a Service does:
    the client sees no EOF while the connection is idle, only a failed read
    after it has sent. Connections opened afterwards are served normally.
    """

    def __init__(self) -> None:
        self._generation = 0
        self._server: asyncio.Server | None = None

    async def __aenter__(self) -> str:
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        port = self._server.sockets[0].getsockname()[1]
        return f"redis://127.0.0.1:{port}/0"

    async def __aexit__(self, *exc: object) -> None:
        assert self._server is not None
        self._server.close()

    def restart(self) -> None:
        self._generation += 1

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        born = self._generation
        while await self._read_command(reader):
            if born != self._generation:
                writer.transport.abort()
                return
            writer.write(b"+PONG\r\n")
            await writer.drain()
        writer.close()

    @staticmethod
    async def _read_command(reader: asyncio.StreamReader) -> bool:
        header = await reader.readline()  # *<argc>
        if not header:
            return False
        for _ in range(int(header[1:])):
            await reader.readline()  # $<len>
            await reader.readline()  # the argument
        return True


async def test_pooled_connection_dead_after_restart_is_replaced():
    """SES-14 (#85): the first command after a restart reconnects instead of failing."""
    store = RestartingStore()
    async with store as url:
        client = create_redis(url)
        assert await client.ping() is True
        store.restart()
        assert await client.ping() is True
        await client.aclose()


async def test_without_retry_the_same_restart_fails():
    """The fixture reproduces the fault: a client with no retry fails on that command."""
    store = RestartingStore()
    async with store as url:
        client = Redis.from_url(url, decode_responses=True)
        assert await client.ping() is True
        store.restart()
        with pytest.raises(ConnectionError):
            await client.ping()
        await client.aclose()


def test_client_health_checks_idle_connections():
    client = create_redis("redis://127.0.0.1:6379/0")
    kwargs = client.connection_pool.connection_kwargs
    assert kwargs["health_check_interval"] > 0
    assert kwargs["retry"].get_retries() >= 1
