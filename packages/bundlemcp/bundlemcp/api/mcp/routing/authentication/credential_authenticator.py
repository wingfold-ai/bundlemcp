from typing import Protocol, runtime_checkable

from fastapi import Request

from bundlemcp.api.mcp.routing.authentication.authentication_outcome import (
    AuthenticationOutcome,
)
from bundlemcp.application.auth.auth_service import AuthService
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
    ) -> AuthenticationOutcome:
        """Who a credential of this kind on the request proves the caller to be, if anyone."""
        ...
