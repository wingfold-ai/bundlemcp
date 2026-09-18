from enum import StrEnum


class ResponseType(StrEnum):
    """What the authorization endpoint may return; only the code flow is served."""

    CODE = "code"
