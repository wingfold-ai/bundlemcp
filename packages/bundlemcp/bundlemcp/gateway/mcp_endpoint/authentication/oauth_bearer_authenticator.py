from fastapi import Request

from bundlemcp.gateway.composition import BundleView
from bundlemcp.models import CallerIdentity, EndpointAuthMode
from bundlemcp.services import AuthService


class OAuthBearerAuthenticator:
    """An access token this gateway issued for exactly this endpoint."""

    mode = EndpointAuthMode.OAUTH

    async def authenticate(
        self, request: Request, view: BundleView, auth: AuthService
    ) -> CallerIdentity | None:
        return await auth.authenticate_oauth_bearer(
            authorization=request.headers.get("authorization"), endpoint_id=view.endpoint.id
        )
