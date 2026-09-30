"""Whether an upstream URL points at the gateway's own network."""

import ipaddress
from urllib.parse import urlparse

# Names that never resolve on the public internet: RFC 6761/6762 reserved suffixes, and
# Kubernetes service names. Kept in step with the web client's connectionKind().
PRIVATE_SUFFIXES = (".localhost", ".local", ".internal", ".svc")


def is_internal_host(url: str) -> bool:
    """A dotless or private-use host name, or a private, loopback or link-local address.

    Such a host is a compose service, a cluster-internal name or a machine
    on the operator's own network, rather than a third party on the internet.
    """
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    if host == "localhost" or host.endswith(PRIVATE_SUFFIXES):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return "." not in host
    return address.is_private or address.is_loopback or address.is_link_local
