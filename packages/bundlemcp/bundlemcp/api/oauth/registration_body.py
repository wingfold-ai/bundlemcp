"""Reading a client registration request so a bad one fails the way RFC 7591 describes."""

from typing import Annotated

from fastapi import Depends, Request
from pydantic import ValidationError

from bundlemcp.application.errors import OAuthError
from bundlemcp.application.schemas import ClientRegistrationRequest
from bundlemcp.domain.oauth.oauth_error_code import OAuthErrorCode


async def registration_body(request: Request) -> ClientRegistrationRequest:
    """The validated body, or the protocol's own refusal instead of the framework's.

    FastAPI would answer a body it cannot validate with a 422 in its own error
    shape, which an OAuth client does not understand. RFC 7591 section 3.2.2
    wants a 400 carrying ``invalid_client_metadata``, so the body is read here
    and every validation failure — an unsupported grant type, an unknown
    application type, a missing field, or no JSON at all — becomes that error.
    """
    try:
        payload = await request.json()
    except ValueError:
        raise OAuthError(
            OAuthErrorCode.INVALID_CLIENT_METADATA, "request body is not JSON"
        ) from None
    try:
        return ClientRegistrationRequest.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(part) for part in first["loc"]) or "body"
        raise OAuthError(
            OAuthErrorCode.INVALID_CLIENT_METADATA, f"{field}: {first['msg']}"
        ) from None


RegistrationBodyProvider = Annotated[ClientRegistrationRequest, Depends(registration_body)]
