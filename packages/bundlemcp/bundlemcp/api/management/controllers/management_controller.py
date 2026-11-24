from fastapi import Depends, params

from bundlemcp.api.http.controller import Controller
from bundlemcp.api.http.management_auth import ManagementAuth
from bundlemcp.api.http.route import RouteSpec


class ManagementController(Controller):
    """A controller every route of which requires management credentials.

    Each route declares the access it needs (``access=`` on its route decorator: a key
    scope, or ``FULL``), and the admin-session-or-service-key check is attached per route
    with that access. A route without a declaration is refused when the controller is
    built, so nothing is reachable by a scoped key unless a route says so.
    """

    def __init__(self) -> None:
        super().__init__()

    def _route_dependencies(self, name: str, spec: RouteSpec) -> list[params.Depends]:
        if spec.access is None:
            raise TypeError(
                f"{type(self).__name__}.{name} declares no access; give its route decorator "
                "access=<scope> or access=FULL"
            )
        return [Depends(ManagementAuth(spec.access))]
