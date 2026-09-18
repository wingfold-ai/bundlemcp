from enum import StrEnum


class TokenEndpointAuthMethod(StrEnum):
    """How a client proves itself at the token endpoint.

    A public client (``NONE``) has no secret and relies on PKCE; a confidential
    client presents its secret in the Basic header or in the form body.
    """

    NONE = "none"
    CLIENT_SECRET_BASIC = "client_secret_basic"
    CLIENT_SECRET_POST = "client_secret_post"
