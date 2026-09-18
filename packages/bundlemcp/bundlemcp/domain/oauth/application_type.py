from enum import StrEnum


class ApplicationType(StrEnum):
    """What kind of program a registering client says it is.

    RFC 7591 takes these two values from OpenID Connect Dynamic Client
    Registration and defines no others, so a registration naming anything else
    is refused as invalid client metadata.
    """

    # Runs on a server its operator controls: it can keep a client secret, and
    # its redirect URIs are https URLs.
    WEB = "web"
    # Runs on the end user's own device — a desktop, mobile or CLI program.
    # Anything shipped to the user can be read out of the binary, so such a
    # client keeps no secret: it proves itself with PKCE and redirects to a
    # custom scheme or a loopback address.
    NATIVE = "native"
