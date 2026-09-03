from typing import Protocol, runtime_checkable

from fastapi import Request

from bundlemcp.gateway.composition import BundleView
from bundlemcp.models import CallerIdentity, EndpointAuthMode
from bundlemcp.services import AuthService


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
