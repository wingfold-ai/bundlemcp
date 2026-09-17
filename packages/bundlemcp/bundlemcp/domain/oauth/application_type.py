from enum import StrEnum


class ApplicationType(StrEnum):
    """What kind of program a registering client says it is (RFC 7591)."""

    WEB = "web"
    NATIVE = "native"
