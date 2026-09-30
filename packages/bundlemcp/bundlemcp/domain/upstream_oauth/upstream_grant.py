from enum import StrEnum


class UpstreamGrant(StrEnum):
    """How the gateway obtains tokens from an upstream authorization server."""

    AUTHORIZATION_CODE = "authorization_code"  # a person signs in through the browser
    CLIENT_CREDENTIALS = "client_credentials"  # the gateway authenticates as itself
