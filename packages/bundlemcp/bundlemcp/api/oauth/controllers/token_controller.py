"""The token endpoint and revocation: the two routes a client authenticates itself on."""

from typing import Annotated

from fastapi import Depends, Form, Request, Response

from bundlemcp.api.http.controller import Controller
from bundlemcp.api.http.route import route
from bundlemcp.api.oauth.auth_lockout import AuthLockout
from bundlemcp.api.oauth.count_credential_failure import count_credential_failure
from bundlemcp.api.oauth.presented_client_credentials import ClientCredentialsProvider
from bundlemcp.api.oauth.presented_token_request import TokenRequestProvider
from bundlemcp.api.oauth.providers import AuthFailureGuardProvider, TokenServiceProvider
from bundlemcp.application.errors import OAuthError
from bundlemcp.application.schemas import RevocationResponse, TokenResponse
from bundlemcp.domain.oauth.oauth_error_code import OAuthErrorCode

# A refused credential or grant is a credential-scan signal; a malformed request is not.
CREDENTIAL_ERRORS = frozenset({OAuthErrorCode.INVALID_CLIENT, OAuthErrorCode.INVALID_GRANT})
NO_STORE = {"Cache-Control": "no-store"}


class OAuthTokenController(Controller):
    """Every route here refuses a locked-out client before reading its credentials."""

    prefix = "/oauth"
    tags = ("oauth",)
    include_in_schema = False

    def __init__(self) -> None:
        super().__init__(dependencies=[Depends(AuthLockout())])  # EP-20

    @route.post("/token")
    async def token(
        self,
        request: Request,
        service: TokenServiceProvider,
        auth_failures: AuthFailureGuardProvider,
        credentials: ClientCredentialsProvider,
        grant: TokenRequestProvider,
    ) -> Response:
        try:
            tokens: TokenResponse = await service.exchange(credentials, grant)
        except OAuthError as exc:
            if exc.code in CREDENTIAL_ERRORS:
                await count_credential_failure(request, auth_failures)
            raise
        return Response(tokens.model_dump_json(), media_type="application/json", headers=NO_STORE)

    @route.post("/revoke")
    async def revoke(
        self,
        request: Request,
        service: TokenServiceProvider,
        auth_failures: AuthFailureGuardProvider,
        credentials: ClientCredentialsProvider,
        token: Annotated[str, Form()],
    ) -> Response:
        """RFC 7009: the authenticated client revokes its own access or refresh token.

        Always 200 for a token that is unknown or not the client's; 401 for a
        client that cannot authenticate, counted like any credential failure.
        """
        try:
            await service.revoke(credentials, token)
        except OAuthError:
            await count_credential_failure(request, auth_failures)
            raise
        return Response(
            RevocationResponse().model_dump_json(), media_type="application/json", headers=NO_STORE
        )
