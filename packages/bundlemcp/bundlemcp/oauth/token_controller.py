"""The token endpoint and its companions: exchange, introspection, revocation."""

from typing import Annotated

from fastapi import Form, HTTPException, Request, Response

from bundlemcp.http import Controller, route
from bundlemcp.oauth.oauth_error_response import oauth_error_response
from bundlemcp.oauth.providers import (
    AuthFailureGuardProvider,
    IntrospectionServiceProvider,
    TokenServiceProvider,
)
from bundlemcp.providers import AuthServiceProvider
from bundlemcp.schemas import IntrospectionResponse, RevocationResponse, TokenResponse
from bundlemcp.services.errors import OAuthError
from bundlemcp.services.oauth_server import ClientCredentials, TokenRequest

CREDENTIAL_ERRORS = frozenset({"invalid_client", "invalid_grant"})


class OAuthTokenController(Controller):
    prefix = "/oauth"
    tags = ("oauth",)
    include_in_schema = False

    @route.post("/token")
    async def token(  # noqa: PLR0913 - one form field per RFC 6749 parameter
        self,
        request: Request,
        service: TokenServiceProvider,
        auth_failures: AuthFailureGuardProvider,
        grant_type: Annotated[str, Form()],
        code: Annotated[str | None, Form()] = None,
        redirect_uri: Annotated[str | None, Form()] = None,
        code_verifier: Annotated[str | None, Form()] = None,
        refresh_token: Annotated[str | None, Form()] = None,
        client_id: Annotated[str | None, Form()] = None,
        client_secret: Annotated[str | None, Form()] = None,
    ) -> Response:
        credentials = ClientCredentials.from_basic_header(
            request.headers.get("authorization")
        ) or ClientCredentials(client_id=client_id or "", client_secret=client_secret)
        token_request = TokenRequest(
            grant_type=grant_type,
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            refresh_token=refresh_token,
        )
        try:
            tokens: TokenResponse = await service.exchange(credentials, token_request)
        except OAuthError as exc:
            if exc.error in CREDENTIAL_ERRORS:
                # RATE-5: a failed grant is a credential-scan signal
                result = await auth_failures.record(request)
                if not result.allowed:
                    locked = oauth_error_response(
                        "too_many_requests", "too many authentication failures", status=429
                    )
                    locked.headers["Retry-After"] = str(result.retry_after)
                    return locked
            return oauth_error_response(exc.error, exc.description, status=exc.status)
        return Response(
            tokens.model_dump_json(),
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
        )

    @route.post("/introspect", response_model_exclude_none=True)
    async def introspect(
        self,
        request: Request,
        auth: AuthServiceProvider,
        service: IntrospectionServiceProvider,
        token: Annotated[str, Form()],
    ) -> IntrospectionResponse:
        """Requires a service API key; reports sub + endpoint audience.

        Upstream resource servers doing RFC 7662 client auth (HTTP Basic) may
        supply the service key as the client secret.
        """
        caller = await auth.authenticate_api_key(
            authorization=request.headers.get("authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )
        if caller is None:
            basic = ClientCredentials.from_basic_header(request.headers.get("authorization"))
            caller = await auth.resolve_api_key(basic.client_secret if basic else None)
        if caller is None or not caller.is_service_key:
            raise HTTPException(401, "service API key required")
        return await service.introspect(token)

    @route.post("/revoke")
    async def revoke(
        self, service: TokenServiceProvider, token: Annotated[str, Form()]
    ) -> RevocationResponse:
        """RFC 7009: revokes by access or refresh token; always 200."""
        await service.revoke(token)
        return RevocationResponse()
