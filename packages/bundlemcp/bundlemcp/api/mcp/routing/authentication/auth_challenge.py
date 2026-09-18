from fastapi import Response
from fastapi.responses import JSONResponse

from bundlemcp.domain.endpoints.endpoint_resource import EndpointResource


def unauthorized_challenge(public_base: str, endpoint_name: str) -> Response:
    """401 with the challenge + per-endpoint protected-resource metadata (RFC 9728)."""
    metadata = EndpointResource(public_base=public_base, endpoint_name=endpoint_name).metadata_url
    return JSONResponse(
        {"error": "unauthorized"},
        status_code=401,
        headers={"WWW-Authenticate": f'Bearer resource_metadata="{metadata}"'},
    )
