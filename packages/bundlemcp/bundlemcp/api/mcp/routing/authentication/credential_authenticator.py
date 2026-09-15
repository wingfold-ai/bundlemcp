from typing import Protocol, runtime_checkable

from fastapi import Request

from bundlemcp.application.auth.auth_service import AuthService
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.bundles.bundle_view import BundleView
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode


@runtime_checkable
class CredentialAuthenticator(Protocol):
    """One way a caller may prove who they are on an endpoint."""

    @property
    def mode(self) -> EndpointAuthMode:
        """The endpoint auth mode this authenticator implements."""
        ...

    async def authenticate(
        self, request: Request, view: BundleView, auth: AuthService
    ) -> CallerIdentity | None:
        """The caller's identity if the request carries a valid credential of this kind."""
        ...
