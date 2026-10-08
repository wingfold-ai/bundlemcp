"""The CSP source expression that lets a form's answer redirect to a client."""

import re
from urllib.parse import urlsplit

# Characters a CSP host-source may carry: no wildcard, no IPv6 literal.
_HOST = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?")
# Path characters that cannot end the source expression or the directive early.
_PATH = re.compile(r"[A-Za-z0-9\-._~!$&()*+=:@%/]*")


def form_action_source(redirect_uri: str) -> str | None:
    """The source expression admitting a redirect to ``redirect_uri``, or None.

    It is the URI's scheme, host, explicit port and path, with the query and
    fragment dropped, so it names that one callback rather than a wildcard or a
    bare scheme. None when the URI cannot be written as a source expression
    (an unexpected scheme, userinfo, an IPv6 literal, or a path holding a
    character that would end the expression), so the caller keeps the page
    same-origin instead of loosening the policy.
    """
    try:
        parts = urlsplit(redirect_uri)
        port = parts.port
    except ValueError:
        return None
    host = parts.hostname or ""
    if (
        parts.scheme not in ("https", "http")
        or "@" in parts.netloc
        or not _HOST.fullmatch(host)
        or not _PATH.fullmatch(parts.path)
    ):
        return None
    authority = host if port is None else f"{host}:{port}"
    return f"{parts.scheme}://{authority}{parts.path}"
