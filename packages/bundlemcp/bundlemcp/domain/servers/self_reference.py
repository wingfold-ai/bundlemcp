"""Whether an upstream URL is one of this gateway's own MCP endpoints.

A bundle that included such an upstream would call itself: every tool call
would re-enter the gateway until a timeout stopped it. The rule recognises the
gateway only under its public URL; reached under another host name (an
internal service name, a second domain, a proxy) it cannot be told apart from
the URL alone.
"""

import re
from urllib.parse import urlsplit

DEFAULT_PORTS = {"http": 80, "https": 443}
ENDPOINT_SEGMENT = re.compile(r"/[^/]+/mcp")


def _origin(url: str) -> tuple[str, str, int | None] | None:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if not parts.hostname:
        return None
    try:
        port = parts.port or DEFAULT_PORTS.get(scheme)
    except ValueError:
        return None
    return scheme, parts.hostname.lower(), port


def self_reference_refusal(server_name: str, url: str) -> str:
    """Why an upstream that is the gateway itself cannot be a bundle member."""
    return (
        f"upstream {server_name!r} at {url} is one of this gateway's own MCP endpoints; "
        "a bundle cannot include the gateway itself (BND-5)"
    )


def addresses_gateway_endpoint(url: str, public_base: str) -> bool:
    """True when ``url`` is ``{public_base}/{name}/mcp`` for any endpoint name, in any spelling.

    The origin must match the public URL's (host compared case-insensitively,
    a default port explicit or implied), and the path must be exactly one
    segment and ``/mcp`` under the public URL's path; a trailing slash is
    ignored. A name that is not an endpoint yet counts too, so an endpoint
    created later is covered.
    """
    origin = _origin(url)
    if origin is None or origin != _origin(public_base):
        return False
    prefix = urlsplit(public_base.strip()).path.rstrip("/")
    path = urlsplit(url.strip()).path.rstrip("/")
    if not path.startswith(prefix):
        return False
    return ENDPOINT_SEGMENT.fullmatch(path[len(prefix) :]) is not None
