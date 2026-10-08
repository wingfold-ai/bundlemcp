"""Which namespace a user's subject is drawn from when the gateway names them upstream."""

from enum import StrEnum


class IdentitySubject(StrEnum):
    """The identifier a user is named by toward upstream servers.

    ``INTERNAL`` is the gateway's own user id, stable within one gateway database.
    ``OIDC`` is the identity provider's subject, stable wherever that provider is.
    """

    INTERNAL = "internal"
    OIDC = "oidc"
