"""One entry of an operator's redirect-URI allow-list, and what it matches."""

import re
from urllib.parse import SplitResult, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

WILDCARD_LABEL = "*"
# A DNS label as the wildcard may stand for it: letters, digits and inner hyphens.
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class RedirectUriPattern(BaseModel):
    """An exact redirect URI, or one whose leftmost host label is the wildcard ``*``.

    An exact entry matches a redirect URI that is the same string, character
    for character, as OAuth compares redirect URIs. A wildcard entry such as
    ``https://*.example.com/oauth/callback`` matches a URI with the same scheme,
    port, path and query whose host is exactly one DNS label in front of the
    rest: ``https://a.example.com/oauth/callback`` matches, while
    ``https://example.com/oauth/callback`` and
    ``https://a.b.example.com/oauth/callback`` do not. The wildcard appears
    nowhere else, and the host after it has at least two labels, so an entry
    cannot cover a whole top-level domain.
    """

    model_config = ConfigDict(frozen=True)

    pattern: str = Field(
        min_length=1,
        description="An absolute http(s) redirect URI, optionally with '*' as its whole "
        "leftmost host label (e.g. 'https://*.example.com/oauth/callback')",
    )

    @field_validator("pattern")
    @classmethod
    def _check_syntax(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError(f"{value!r} is not an absolute http(s) URI")
        if "@" in parts.netloc or parts.fragment:
            raise ValueError(f"{value!r} must not carry user information or a fragment")
        host_labels = parts.hostname.split(".")
        if WILDCARD_LABEL in value.replace(f"//{WILDCARD_LABEL}.", "//", 1):
            raise ValueError(f"{value!r} may use '*' only as the whole leftmost host label")
        if host_labels[0] == WILDCARD_LABEL and len(host_labels) < 3:
            raise ValueError(f"{value!r} must name at least two host labels after '*.'")
        try:
            parts.port  # noqa: B018 - parsing the port is the check
        except ValueError:
            raise ValueError(f"{value!r} has an invalid port") from None
        return value

    @property
    def wildcard_domain(self) -> str | None:
        """The domain a wildcard entry covers one label in front of; None for an exact entry."""
        host = urlsplit(self.pattern).hostname or ""
        prefix = f"{WILDCARD_LABEL}."
        return host.removeprefix(prefix) if host.startswith(prefix) else None

    def matches(self, uri: str) -> bool:
        """Whether a redirect URI a client presents is covered by this entry."""
        domain = self.wildcard_domain
        if domain is None:
            return uri == self.pattern
        try:
            return self._matches_wildcard(urlsplit(self.pattern), urlsplit(uri), domain)
        except ValueError:  # an unparseable port is not a match
            return False

    @staticmethod
    def _matches_wildcard(pattern: SplitResult, candidate: SplitResult, domain: str) -> bool:
        if "@" in candidate.netloc or candidate.fragment or not candidate.hostname:
            return False
        if (candidate.scheme, candidate.port, candidate.path, candidate.query) != (
            pattern.scheme,
            pattern.port,
            pattern.path,
            pattern.query,
        ):
            return False
        label, dot, rest = candidate.hostname.partition(".")
        return bool(dot) and rest == domain and _DNS_LABEL.match(label) is not None
