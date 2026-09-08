from fastapi import Request

from bundlemcp.application.auth.auth_service import AuthService
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.bundles.bundle_view import BundleView
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode


class ApiKeyAuthenticator:
    """A gateway API key, in the Authorization header or X-API-Key, scoped to this endpoint."""

    mode = EndpointAuthMode.API_KEY

    async def authenticate(
        self, request: Request, view: BundleView, auth: AuthService
    ) -> CallerIdentity | None:
        key = await auth.authenticate_api_key(
            authorization=request.headers.get("authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )
        if key is None or not key.reaches(view.endpoint.id):  # KEY-2
            return None
        return CallerIdentity.with_api_key(key.id)
