"""Client-IP derivation behind a reverse proxy.

X-Forwarded-For is honored ONLY when the direct socket peer is a configured
trusted proxy; otherwise the socket peer is used. When trusted, the leftmost
XFF entry (the original client) is taken. XFF from an untrusted peer is never
believed — it is a spoofing vector.
"""

import ipaddress

from fastapi import Request

from bundlemcp.application.settings.settings import Settings


def _peer_trusted(peer: str, settings: Settings) -> bool:
    if not settings.trusted_proxies:
        return False
    try:
        addr = ipaddress.ip_address(peer)
    except ValueError:
        return False
    for cidr in settings.trusted_proxies:
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def client_ip(request: Request, settings: Settings) -> str:
    peer = request.client.host if request.client else "unknown"
    if _peer_trusted(peer, settings):
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()  # leftmost = original client
    return peer
