from enum import StrEnum


class ServerAuthMode(StrEnum):
    """How the gateway authenticates to an upstream server."""

    NONE = "none"
    STATIC_HEADERS = "static_headers"
    UPSTREAM_OAUTH = "upstream_oauth"
    DELEGATED_TOKEN = "delegated_token"

    def settled(self, *, has_static_headers: bool) -> "ServerAuthMode":
        """The mode a server is stored with, given whether it holds static headers.

        ``none`` and ``static_headers`` differ only in whether headers are
        stored, so either one requested becomes the one the headers say.
        """
        if self in {ServerAuthMode.UPSTREAM_OAUTH, ServerAuthMode.DELEGATED_TOKEN}:
            return self
        return ServerAuthMode.STATIC_HEADERS if has_static_headers else ServerAuthMode.NONE
