from fastapi import Response
from fastapi.responses import JSONResponse


def unauthorized_challenge(public_base: str, endpoint_name: str) -> Response:
    """401 with the challenge + per-endpoint protected-resource metadata (RFC 9728)."""
    metadata = f"{public_base}/.well-known/oauth-protected-resource/{endpoint_name}/mcp"
    return JSONResponse(
        {"error": "unauthorized"},
        status_code=401,
        headers={"WWW-Authenticate": f'Bearer resource_metadata="{metadata}"'},
    )
