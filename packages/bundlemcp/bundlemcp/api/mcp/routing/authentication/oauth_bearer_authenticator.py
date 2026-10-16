from fastapi import Request

from bundlemcp.api.mcp.routing.authentication.authentication_outcome import (
    AuthenticationOutcome,
)
from bundlemcp.application.auth.auth_service import AuthService
from bundlemcp.domain.bundles.bundle_view import BundleView
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode


class OAuthBearerAuthenticator:
    """An access token this gateway issued for exactly this endpoint."""

    mode = EndpointAuthMode.OAUTH

    async def authenticate(
        self, request: Request, view: BundleView, auth: AuthService
    ) -> AuthenticationOutcome:
        bearer = await auth.resolve_oauth_bearer(authorization=request.headers.get("authorization"))
        if bearer is None:
            return AuthenticationOutcome.nobody()
        if bearer.endpoint_id != view.endpoint.id:  # issued for another endpoint
            return AuthenticationOutcome.not_entitled(bearer.identity)
        return AuthenticationOutcome.authenticated(bearer.identity)
