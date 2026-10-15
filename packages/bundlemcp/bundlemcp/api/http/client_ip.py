"""Client-IP derivation behind a reverse proxy.

X-Forwarded-For is honored ONLY when the direct socket peer is a configured
trusted proxy; otherwise the socket peer is used. From a trusted peer the list
is read from the right: each proxy appends the address it saw, so the first
entry that is not itself a trusted proxy is the client. Entries to its left
were written by the client and are never believed. When every entry is a
trusted proxy, the leftmost is taken.

This is the only reader of forwarding headers: X-Forwarded-Proto and
X-Forwarded-Host are ignored, because every published URL is built from the
public URL rather than from the request.
"""

import ipaddress
from collections.abc import Sequence

from fastapi import Request

from bundlemcp.application.settings.settings import Settings

type IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def _parse(value: str) -> IpAddress | None:
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _trusted(addr: IpAddress | None, settings: Settings) -> bool:
    if addr is None:
        return False
    for cidr in settings.trusted_proxies:
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def _forwarded_for(request: Request) -> list[str]:
    """Every X-Forwarded-For entry in order, across repeated headers."""
    headers = request.headers
    values: Sequence[str] = (
        headers.getlist("x-forwarded-for")
        if hasattr(headers, "getlist")
        else [v for v in [headers.get("x-forwarded-for")] if v]
    )
    return [entry.strip() for value in values for entry in value.split(",") if entry.strip()]


def client_ip(request: Request, settings: Settings) -> str:
    peer = request.client.host if request.client else "unknown"
    if not _trusted(_parse(peer), settings):
        return peer
    entries = _forwarded_for(request)
    for entry in reversed(entries):
        addr = _parse(entry)
        if _trusted(addr, settings):
            continue
        # A proxy we trust wrote this entry; one it could not parse is not an address to count.
        return str(addr) if addr is not None else peer
    if entries and (leftmost := _parse(entries[0])) is not None:
        return str(leftmost)
    return peer
