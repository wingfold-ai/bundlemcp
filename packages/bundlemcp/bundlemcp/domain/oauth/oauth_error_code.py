from enum import StrEnum


class OAuthErrorCode(StrEnum):
    """The error codes this authorization server answers with.

    RFC 6749 section 5.2 names the token endpoint's, section 4.1.2.1 the
    authorization endpoint's, RFC 7591 section 3.2.2 registration's and
    RFC 8707 section 2 the resource parameter's. ``TOO_MANY_REQUESTS`` is
    the gateway's own, for a client locked out after repeated bad credentials.
    """

    INVALID_REQUEST = "invalid_request"
    INVALID_CLIENT = "invalid_client"
    INVALID_GRANT = "invalid_grant"
    UNAUTHORIZED_CLIENT = "unauthorized_client"
    UNSUPPORTED_GRANT_TYPE = "unsupported_grant_type"
    UNSUPPORTED_RESPONSE_TYPE = "unsupported_response_type"
    INVALID_SCOPE = "invalid_scope"
    ACCESS_DENIED = "access_denied"
    INVALID_TARGET = "invalid_target"
    INVALID_CLIENT_METADATA = "invalid_client_metadata"
    INVALID_REDIRECT_URI = "invalid_redirect_uri"
    TOO_MANY_REQUESTS = "too_many_requests"
