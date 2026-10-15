"""Which browser origins may use an endpoint from another site.

Not authentication: a browser sets ``Origin`` itself and a page cannot forge it,
but any other client sends whatever it likes. The rule decides only which web
pages may drive a visitor's browser against an endpoint; the caller is still
authenticated by the endpoint's auth modes.
"""

from collections.abc import Iterable
from urllib.parse import urlsplit

from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode

ANY_ORIGIN = "*"
DEFAULT_PORTS = {"http": 80, "https": 443}


def normalise_origin(entry: str) -> str:
    """An origin in its compared form, or a ValueError naming the entry.

    Scheme and host are lower-cased, a scheme's default port and a trailing
    slash are dropped. A path, query, fragment, credentials or a scheme other
    than http(s) make the entry invalid.
    """
    raw = entry.strip()
    parts = urlsplit(raw.rstrip("/"))
    try:
        port = parts.port
    except ValueError:
        raise ValueError(f"{entry!r} is not an origin: invalid port") from None
    if parts.scheme.lower() not in DEFAULT_PORTS or not parts.hostname:
        raise ValueError(f"{entry!r} is not an origin: expected http(s)://host[:port]")
    if parts.path or parts.query or parts.fragment or parts.username or parts.password:
        raise ValueError(f"{entry!r} is not an origin: it may not have a path, query or user")
    scheme = parts.scheme.lower()
    host = parts.hostname.lower()
    if ":" in host:  # an IPv6 literal keeps its brackets
        host = f"[{host}]"
    if port is None or port == DEFAULT_PORTS[scheme]:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def normalise_allowed_origins(entries: Iterable[str]) -> list[str]:
    """The list as stored: ``["*"]`` alone, or normalised origins without duplicates."""
    entries = list(entries)
    if ANY_ORIGIN in entries:
        if len(entries) > 1:
            raise ValueError("'*' allows every origin and cannot be combined with other entries")
        return [ANY_ORIGIN]
    result: list[str] = []
    for entry in entries:
        origin = normalise_origin(entry)
        if origin not in result:
            result.append(origin)
    return result


def default_allowed_origins(auth_modes: Iterable[EndpointAuthMode]) -> list[str]:
    """Open endpoints refuse cross-site browsers; endpoints that need a credential allow any."""
    return [] if set(auth_modes) == {EndpointAuthMode.NONE} else [ANY_ORIGIN]


def origin_allowed(origin: str, allowed: list[str], public_origin: str) -> bool:
    """Whether a request carrying this ``Origin`` header may use the endpoint.

    The gateway's own public origin is always allowed. ``null`` (a sandboxed
    page or a file) and anything unparsable match only ``*``.
    """
    if ANY_ORIGIN in allowed:
        return True
    try:
        candidate = normalise_origin(origin)
    except ValueError:
        return False
    return candidate == normalise_origin(public_origin) or candidate in allowed
