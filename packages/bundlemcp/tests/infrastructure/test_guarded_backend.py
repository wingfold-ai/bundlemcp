"""The egress policy enforced on the address a connection dials (SEC-2)."""

import ipaddress

import httpcore
import httpcore2
import pytest
from bundlemcp.infrastructure.config.settings import EnvSettings
from bundlemcp.infrastructure.egress.egress_policy import EgressDenied
from bundlemcp.infrastructure.egress.egress_scope import EgressScope
from bundlemcp.infrastructure.egress.guarded_backend import GuardedNetworkBackend, guard_pool


class Stop(Exception):
    """Ends a request once the part under test has run."""


class FakeStream:
    def __init__(self, log: list) -> None:
        self._log = log

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        self._log.append(("tls", server_hostname))
        raise Stop

    async def write(self, buffer, timeout=None):
        raise Stop

    async def read(self, max_bytes, timeout=None):
        raise Stop

    async def aclose(self):
        pass

    def get_extra_info(self, info):
        return None


class FakeNetwork:
    """Records every dial instead of opening a socket."""

    def __init__(self) -> None:
        self.log: list = []

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self.log.append(("dial", host, port))
        return FakeStream(self.log)

    async def sleep(self, seconds):
        pass


def answers(*sequence: str):
    """A resolver giving the next answer on each lookup, then repeating the last."""
    lookups: list[str] = []

    async def resolve(host, port):
        lookups.append(host)
        answer = sequence[min(len(lookups), len(sequence)) - 1]
        return [ipaddress.ip_address(answer)]

    resolve.lookups = lookups  # type: ignore[attr-defined]
    return resolve


def guarded_pool(network: FakeNetwork, resolver, module=httpcore, **settings):
    pool = module.AsyncConnectionPool(network_backend=network)
    guard_pool(pool, EnvSettings(_env_file=None, **settings), resolver)
    return pool


async def test_sec2_the_vetted_address_is_the_one_dialled():
    """SEC-2: the pool never resolves the name again; it dials the address the policy judged."""
    network = FakeNetwork()
    resolver = answers("10.0.0.5", "169.254.169.254")
    with pytest.raises(Stop):
        await guarded_pool(network, resolver).request("GET", "http://upstream.example/mcp")
    assert network.log[0] == ("dial", "10.0.0.5", 80)
    assert resolver.lookups == ["upstream.example"]


async def test_sec2_rebinding_to_metadata_is_refused_before_dialling():
    """SEC-2: a name that answers a blocked address at connect time is never dialled."""
    network = FakeNetwork()
    with pytest.raises(EgressDenied):
        await guarded_pool(network, answers("169.254.169.254")).request(
            "GET", "http://upstream.example/mcp"
        )
    assert network.log == []


async def test_sec2_tls_still_verifies_the_host_name():
    """SEC-2: an https connection dials the vetted IP but starts TLS with the host name."""
    network = FakeNetwork()
    with pytest.raises(Stop):
        await guarded_pool(network, answers("10.0.0.5")).request(
            "GET", "https://upstream.example/mcp"
        )
    assert network.log == [("dial", "10.0.0.5", 443), ("tls", "upstream.example")]


async def test_sec2_the_guard_covers_the_mcp_clients_pool_too():
    """SEC-2: the MCP client's connection pool is guarded the same way."""
    network = FakeNetwork()
    with pytest.raises(EgressDenied):
        await guarded_pool(network, answers("::ffff:127.0.0.1"), module=httpcore2).request(
            "GET", "http://upstream.example/mcp"
        )
    assert network.log == []


async def test_sec2_an_allow_entry_still_wins_at_connect_time():
    network = FakeNetwork()
    with pytest.raises(Stop):
        await guarded_pool(
            network, answers("127.0.0.1"), egress_allow_cidrs=["127.0.0.0/8"]
        ).request("GET", "http://localhost:9000/mcp")
    assert network.log[0] == ("dial", "127.0.0.1", 9000)


def test_sec2_a_pool_without_a_backend_is_not_used_unguarded():
    with pytest.raises(RuntimeError):
        guard_pool(object(), EnvSettings(_env_file=None))
    pool = httpcore.AsyncConnectionPool()
    settings = EnvSettings(_env_file=None)
    guard_pool(pool, settings)
    guard_pool(pool, settings)
    assert isinstance(pool._network_backend, GuardedNetworkBackend)
    assert not isinstance(pool._network_backend._inner, GuardedNetworkBackend)


class RedirectingStream(FakeStream):
    """Answers every request with a redirect to the https form of the same URL."""

    def __init__(self, log: list) -> None:
        super().__init__(log)
        self._sent = False

    async def write(self, buffer, timeout=None):
        self._sent = True

    async def read(self, max_bytes, timeout=None):
        if not self._sent:
            return b""
        self._sent = False
        return (
            b"HTTP/1.1 307 Temporary Redirect\r\n"
            b"Location: https://upstream.example/mcp\r\nContent-Length: 0\r\n\r\n"
        )


class RedirectingNetwork(FakeNetwork):
    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self.log.append(("dial", host, port))
        return RedirectingStream(self.log)


async def test_sec2_a_followed_redirect_is_judged_again():
    """SEC-2: the redirect hop the MCP transport follows opens its connection through the guard."""
    from bundlemcp.infrastructure.fastmcp.guarded_mcp_http_client import guarded_mcp_http_client
    from mcp.shared._httpx_utils import next_request_within_origin

    settings = EnvSettings(_env_file=None)
    client = guarded_mcp_http_client(settings)()
    pool = client._transport._pool
    assert isinstance(pool._network_backend, GuardedNetworkBackend)

    network = RedirectingNetwork()
    pool._network_backend = GuardedNetworkBackend(
        network, settings, answers("10.0.0.5", "169.254.169.254")
    )
    async with client:
        response = await client.post("http://upstream.example/mcp", json={})
        assert response.status_code == 307
        follow = next_request_within_origin(response)
        assert follow is not None and follow.url.scheme == "https"
        with pytest.raises(EgressDenied):
            await client.send(follow)
    assert [entry for entry in network.log if entry[0] == "dial"] == [("dial", "10.0.0.5", 80)]


def test_sec2_the_gateways_own_clients_ignore_proxy_variables(monkeypatch):
    """SEC-2: an HTTP_PROXY in the environment cannot route around the guard."""
    from bundlemcp.infrastructure.fastmcp.guarded_mcp_http_client import guarded_mcp_http_client
    from bundlemcp.infrastructure.httpx.guarded_client import guarded_client

    monkeypatch.setenv("HTTP_PROXY", "http://proxy.example:3128")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")
    settings = EnvSettings(_env_file=None)
    for client in (guarded_client(settings), guarded_mcp_http_client(settings)()):
        assert not client._mounts
        assert isinstance(client._transport._pool._network_backend, GuardedNetworkBackend)


def test_sec2_the_mcp_client_never_follows_redirects_itself():
    """SEC-2: only the MCP transport follows redirects, and only within the upstream's origin."""
    from bundlemcp.infrastructure.fastmcp.guarded_mcp_http_client import guarded_mcp_http_client

    client = guarded_mcp_http_client(EnvSettings(_env_file=None))(follow_redirects=True)
    assert client.follow_redirects is False


async def test_auth13_public_scope_refuses_rebinding_to_a_private_address():
    """AUTH-13: a public-scope pool never dials a private address a name answers at connect time."""
    network = FakeNetwork()
    pool = httpcore.AsyncConnectionPool(network_backend=network)
    guard_pool(pool, EnvSettings(_env_file=None), answers("10.0.0.5"), EgressScope.PUBLIC)
    with pytest.raises(EgressDenied):
        await pool.request("GET", "https://client.example/client.json")
    assert network.log == []
