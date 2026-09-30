"""A server name derived from what an upstream or its publisher calls it."""

import ipaddress
import re
from urllib.parse import urlparse

_UNSAFE = re.compile(r"[^a-z0-9_-]+")
_RUNS = re.compile(r"[-_]{2,}")
MAX_SUGGESTED_LENGTH = 40
FALLBACK_NAME = "server"


def suggest_server_name(label: str | None, url: str) -> str:
    """A slug-safe, prefix-friendly name: lower-case, no ``__``, trimmed.

    Registry names such as ``io.github.acme/weather`` keep their last
    segment; with no usable label the URL's host names the server, by the
    label before its domain suffix (``mcp.linear.app`` → ``linear``). An IP
    address names nothing, so it yields the fallback.
    """
    slug = _slug((label or "").rsplit("/", 1)[-1])
    if not slug:
        slug = _slug(_host_label(urlparse(url).hostname or ""))
    return slug or FALLBACK_NAME


def _host_label(host: str) -> str:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        parts = host.split(".")
        return parts[0] if len(parts) < 3 else parts[-2]
    return ""


def _slug(text: str) -> str:
    slug = _UNSAFE.sub("-", text.lower())
    slug = _RUNS.sub("-", slug).strip("-_")
    return slug[:MAX_SUGGESTED_LENGTH].rstrip("-_")
