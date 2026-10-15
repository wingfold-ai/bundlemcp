from fastapi import Response
from fastapi.responses import JSONResponse

from bundlemcp.domain.endpoints.endpoint_resource import EndpointResource


def unauthorized_challenge(
    public_base: str, endpoint_name: str, *, invalid_token: bool = False
) -> Response:
    """401 with the challenge + per-endpoint protected-resource metadata (RFC 9728).

    ``invalid_token`` adds ``error="invalid_token"`` for a bearer that was
    presented and refused (RFC 6750 §3.1), prompting the client to authorise
    again for this endpoint; a request with no credential gets the plain
    challenge. Which refusal reason applied is never said.
    """
    metadata = EndpointResource(public_base=public_base, endpoint_name=endpoint_name).metadata_url
    error = 'error="invalid_token", ' if invalid_token else ""
    return JSONResponse(
        {"error": "invalid_token" if invalid_token else "unauthorized"},
        status_code=401,
        headers={"WWW-Authenticate": f'Bearer {error}resource_metadata="{metadata}"'},
    )


def presents_bearer(authorization: str | None) -> bool:
    """Whether the request carries a bearer credential, valid or not."""
    scheme, _, credential = (authorization or "").partition(" ")
    return scheme.lower() == "bearer" and credential.strip() != ""
