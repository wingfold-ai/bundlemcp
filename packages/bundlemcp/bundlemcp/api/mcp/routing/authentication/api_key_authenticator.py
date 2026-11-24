from fastapi import Request

from bundlemcp.api.mcp.routing.authentication.authentication_outcome import (
    AuthenticationOutcome,
)
from bundlemcp.application.auth.auth_service import AuthService
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.bundles.bundle_view import BundleView
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode


class ApiKeyAuthenticator:
    """A gateway API key, in the Authorization header or X-API-Key, scoped to this endpoint."""

    mode = EndpointAuthMode.API_KEY

    async def authenticate(
        self, request: Request, view: BundleView, auth: AuthService
    ) -> AuthenticationOutcome:
        key = await auth.authenticate_api_key(
            authorization=request.headers.get("authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )
        if key is None:
            return AuthenticationOutcome.nobody()
        holder = CallerIdentity.with_api_key(key.id)
        # a scoped service key calls tools only with the mcp scope
        if not key.calls_endpoints or not key.reaches(view.endpoint.id):
            return AuthenticationOutcome.not_entitled(holder)
        return AuthenticationOutcome.authenticated(holder)
