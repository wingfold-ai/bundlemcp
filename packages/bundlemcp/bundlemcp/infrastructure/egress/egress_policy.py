"""Egress policy for gateway-initiated HTTP.

Default: block link-local/metadata ranges and the gateway's own loopback;
allow private RFC 1918 (compose-network upstreams are the primary use case).
Operators tighten via BUNDLEMCP_EGRESS_DENY_CIDRS / extend via _ALLOW_CIDRS
(allow evaluated first).

The policy is a judgement over one address. It is enforced where a connection
is dialled (see ``guarded_backend``), so the address judged is the address
connected to; ``check_url_allowed`` is only an early refusal with a clear error.
"""

import ipaddress
import socket
from urllib.parse import urlparse

import structlog

from bundlemcp.application.settings.settings import Settings

log = structlog.get_logger(__name__)

type IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

_ALWAYS_BLOCKED = [
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / cloud metadata
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fd00:ec2::254/128"),  # AWS metadata over IPv6
    ipaddress.ip_network("127.0.0.0/8"),  # gateway's own loopback
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("0.0.0.0/8"),  # Linux connects these to the local host
    ipaddress.ip_network("::/128"),
]


class EgressDenied(Exception):
    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"egress denied for {url}: {reason}")


class HostUnresolvable(EgressDenied):
    """The host does not resolve, so the policy has no address to judge."""


def normalised(addr: IpAddress) -> IpAddress:
    """The address the policy judges: an IPv4-mapped IPv6 address is its IPv4 address."""
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return addr.ipv4_mapped
    return addr


def judge_address(addr: IpAddress, target: str, settings: Settings) -> None:
    """Raise EgressDenied when ``addr`` may not be connected to; ``target`` names it in errors."""
    addr = normalised(addr)
    if any(addr in ipaddress.ip_network(c) for c in settings.egress_allow_cidrs):
        return  # explicit allow wins
    for net in _ALWAYS_BLOCKED:
        if addr in net:
            log.warning("egress.denied", target=target, blocked=str(net))
            raise EgressDenied(target, f"address {addr} is in blocked range {net}")
    for net in (ipaddress.ip_network(c) for c in settings.egress_deny_cidrs):
        if addr in net:
            log.warning("egress.denied", target=target, blocked=str(net))
            raise EgressDenied(target, f"address {addr} is in operator deny range {net}")


def resolve(host: str) -> list[IpAddress]:
    """Every address ``host`` resolves to; an IP literal resolves to itself."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise HostUnresolvable(host, f"DNS resolution failed: {exc}") from exc
    return [ipaddress.ip_address(info[4][0]) for info in infos]


def check_url_allowed(url: str, settings: Settings) -> None:
    """Raise EgressDenied if the URL's scheme or any resolved address violates the policy."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise EgressDenied(url, "only http(s) URLs with a host are allowed")
    for addr in resolve(parsed.hostname):
        judge_address(addr, url, settings)
