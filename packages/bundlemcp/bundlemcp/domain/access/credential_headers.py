"""The request headers that carry a credential, and the headers left once they are gone."""

from collections.abc import Mapping


class CredentialHeaders:
    """Header names whose value proves who a caller is, so nothing past admission may read them.

    Covers the client's bearer token, a proxy's credential, browser cookies and
    the gateway's own API-key header. Names compare case-insensitively.
    """

    NAMES = frozenset({"authorization", "proxy-authorization", "cookie", "x-api-key"})

    @classmethod
    def removed_from(cls, headers: Mapping[str, str]) -> dict[str, str]:
        """``headers`` with lower-cased names and without any credential-bearing one."""
        return {
            name.lower(): value for name, value in headers.items() if name.lower() not in cls.NAMES
        }
