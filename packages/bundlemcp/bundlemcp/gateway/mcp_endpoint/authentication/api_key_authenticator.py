from fastapi import Request

from bundlemcp.gateway.composition import BundleView
from bundlemcp.models import CallerIdentity, EndpointAuthMode
from bundlemcp.services import AuthService


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
