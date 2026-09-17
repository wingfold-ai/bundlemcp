"""The grant parameters a token-endpoint request carries (RFC 6749 sections 4.1.3 and 6)."""

from typing import Annotated

from fastapi import Depends, Form

from bundlemcp.application.oauth_server import TokenRequest


def presented_token_request(
    grant_type: Annotated[str, Form()],
    code: Annotated[str | None, Form()] = None,
    redirect_uri: Annotated[str | None, Form()] = None,
    code_verifier: Annotated[str | None, Form()] = None,
    refresh_token: Annotated[str | None, Form()] = None,
) -> TokenRequest:
    return TokenRequest(
        grant_type=grant_type,
        code=code,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
        refresh_token=refresh_token,
    )


TokenRequestProvider = Annotated[TokenRequest, Depends(presented_token_request)]
