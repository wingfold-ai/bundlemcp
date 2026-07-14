from enum import StrEnum


class ServerAuthMode(StrEnum):
    NONE = "none"
    STATIC_HEADERS = "static_headers"
    UPSTREAM_OAUTH = "upstream_oauth"
