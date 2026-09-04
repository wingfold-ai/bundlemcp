from fastapi import Request

from bundlemcp.gateway.composition import BundleView
from bundlemcp.models import CallerIdentity, EndpointAuthMode
from bundlemcp.services import AuthService


class AnonymousAuthenticator:
    """No credential at all, on an endpoint that was deliberately left open."""

    mode = EndpointAuthMode.NONE

    async def authenticate(
        self, request: Request, view: BundleView, auth: AuthService
    ) -> CallerIdentity | None:
        return CallerIdentity.anonymous()
