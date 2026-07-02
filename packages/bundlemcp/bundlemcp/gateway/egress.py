"""Egress policy for gateway-initiated HTTP (SEC-1/SEC-2/SEC-3).

Default: block link-local/metadata ranges and the gateway's own loopback;
allow private RFC 1918 (compose-network upstreams are the primary use case).
Operators tighten via BUNDLEMCP_EGRESS_DENY_CIDRS / extend via _ALLOW_CIDRS
(allow evaluated first). Checks run on all RESOLVED addresses so a hostname
can't smuggle a blocked IP past a name-based check.
"""

import ipaddress
import socket
from urllib.parse import urlparse

import structlog

from bundlemcp.settings import Settings

log = structlog.get_logger(__name__)

_ALWAYS_BLOCKED = [
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / cloud metadata
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("127.0.0.0/8"),  # gateway's own loopback
    ipaddress.ip_network("::1/128"),
]


class EgressDenied(Exception):
    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"egress denied for {url}: {reason}")


def _resolve(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise EgressDenied(host, f"DNS resolution failed: {exc}") from exc
    return [ipaddress.ip_address(info[4][0]) for info in infos]


def check_url_allowed(url: str, settings: Settings) -> None:
    """Raise EgressDenied if any resolved address violates the policy (SEC-2)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise EgressDenied(url, "only http(s) URLs with a host are allowed")

    allow = [ipaddress.ip_network(c) for c in settings.egress_allow_cidrs]
    deny = [ipaddress.ip_network(c) for c in settings.egress_deny_cidrs]

    for addr in _resolve(parsed.hostname):
        if any(addr in net for net in allow):
            continue  # explicit allow wins (SEC-2)
        for net in _ALWAYS_BLOCKED:
            if addr in net:
                log.warning("egress.denied", url=url, blocked=str(net))  # SEC-3
                raise EgressDenied(url, f"address {addr} is in blocked range {net}")
        for net in deny:
            if addr in net:
                log.warning("egress.denied", url=url, blocked=str(net))
                raise EgressDenied(url, f"address {addr} is in operator deny range {net}")
