"""The egress policy enforced where a connection is dialled.

A connection pool asks its network backend to open a TCP connection to a host
name. The guard resolves that name once, judges every address with the policy,
and dials a vetted address itself, so the address judged is the address
connected to: a DNS answer that changes between a check and the connect
(rebinding) never reaches a blocked address, and every connection a followed
redirect opens is judged the same way. The pool still starts TLS with the
original host name, so SNI and certificate verification are unchanged.

The guard wraps the pool's own backend, so it works for both ``httpcore``
(the gateway's ``httpx`` clients) and ``httpcore2`` (the MCP client), which
share this interface.
"""

import ipaddress
import socket
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

import anyio

from bundlemcp.application.settings.settings import Settings
from bundlemcp.infrastructure.egress.egress_policy import (
    EgressDenied,
    HostUnresolvable,
    IpAddress,
    judge_address,
)

type Resolver = Callable[[str, int], Awaitable[list[IpAddress]]]


async def resolve_for_connect(host: str, port: int) -> list[IpAddress]:
    """Every address ``host`` resolves to for a TCP connection, in resolver order, once each."""
    try:
        infos = await anyio.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise HostUnresolvable(host, f"DNS resolution failed: {exc}") from exc
    found: list[IpAddress] = []
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if addr not in found:
            found.append(addr)
    return found


class GuardedNetworkBackend:
    """A pool's network backend that only dials addresses the egress policy allows."""

    def __init__(self, inner: Any, settings: Settings, resolver: Resolver = resolve_for_connect):
        self._inner = inner
        self._settings = settings
        self._resolver = resolver

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> Any:
        target = f"{host}:{port}"
        addresses = await self._resolver(host, port)
        if not addresses:
            raise HostUnresolvable(target, "the host resolved to no address")
        for addr in addresses:
            judge_address(addr, target, self._settings)
        failure: Exception | None = None
        for addr in addresses:
            try:
                return await self._inner.connect_tcp(
                    str(addr),
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except Exception as exc:  # the next vetted address may still answer
                failure = exc
        assert failure is not None
        raise failure

    async def connect_unix_socket(self, path: str, *args: Any, **kwargs: Any) -> Any:
        raise EgressDenied(path, "unix sockets are not reachable through the egress policy")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def guard_pool(pool: Any, settings: Settings, resolver: Resolver = resolve_for_connect) -> None:
    """Put the guard in front of a connection pool's network backend.

    Neither ``httpx`` nor ``httpx2`` lets a transport be given a network
    backend, so the pool's is wrapped in place. Fails closed: a pool without
    the expected attribute raises instead of connecting unguarded.
    """
    inner = getattr(pool, "_network_backend", None)
    if inner is None:
        raise RuntimeError(f"cannot guard {type(pool).__name__}: no network backend to wrap")
    if not isinstance(inner, GuardedNetworkBackend):
        pool._network_backend = GuardedNetworkBackend(inner, settings, resolver)
