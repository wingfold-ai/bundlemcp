"""Who may ask the gateway whether a token is good: a resource server holding a service key."""

from fastapi import HTTPException, Request, status

from bundlemcp.api.http.service_providers import AuthServiceProvider
from bundlemcp.domain.oauth.client_credentials import ClientCredentials


class IntrospectionAuth:
    """Router-level dependency: a service-kind API key, presented any way RFC 7662 allows.

    The key may arrive as a Bearer token, in X-API-Key, or as the password of
    an HTTP Basic pair, which is how a resource server doing client
    authentication sends it.
    """

    async def __call__(self, request: Request, auth: AuthServiceProvider) -> None:
        authorization = request.headers.get("authorization")
        key = await auth.authenticate_api_key(
            authorization=authorization, x_api_key=request.headers.get("x-api-key")
        )
        if key is None:
            basic = ClientCredentials.from_basic_header(authorization)
            key = await auth.resolve_api_key(basic.client_secret if basic else None)
        if key is None or not key.may_introspect:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "service API key with the introspect scope required"
            )
