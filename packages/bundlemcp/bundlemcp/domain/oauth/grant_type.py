from enum import StrEnum


class GrantType(StrEnum):
    """The grants this authorization server supports at its token endpoint."""

    AUTHORIZATION_CODE = "authorization_code"
    REFRESH_TOKEN = "refresh_token"
