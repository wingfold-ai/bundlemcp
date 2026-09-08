from fastapi import Request

from bundlemcp.application.auth.auth_service import AuthService
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.bundles.bundle_view import BundleView
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode


class OAuthBearerAuthenticator:
    """An access token this gateway issued for exactly this endpoint."""

    mode = EndpointAuthMode.OAUTH

    async def authenticate(
        self, request: Request, view: BundleView, auth: AuthService
    ) -> CallerIdentity | None:
        return await auth.authenticate_oauth_bearer(
            authorization=request.headers.get("authorization"), endpoint_id=view.endpoint.id
        )
