from enum import StrEnum


class EndpointProfile(StrEnum):
    DEFAULT = "default"
    OAUTH_ONLY = "oauth_only"
    WRITE_AS_READ = "write_as_read"
