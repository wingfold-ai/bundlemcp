from fastapi import Request

from bundlemcp.application.auth.auth_service import AuthService
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.bundles.bundle_view import BundleView
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode


class AnonymousAuthenticator:
    """No credential at all, on an endpoint that was deliberately left open."""

    mode = EndpointAuthMode.NONE

    async def authenticate(
        self, request: Request, view: BundleView, auth: AuthService
    ) -> CallerIdentity | None:
        return CallerIdentity.anonymous()
