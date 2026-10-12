from fastapi import Depends

from bundlemcp.api.http.controller import Controller
from bundlemcp.api.http.deprecated_route_use import DeprecatedRouteUse
from bundlemcp.api.http.management_auth import management_auth


class ManagementController(Controller):
    """A controller every route of which requires management credentials.

    The admin-session-or-service-key check is attached once at the router, so a
    route added to a subclass cannot forget it. A deprecated alias of a route
    also records who still calls it.
    """

    def __init__(self) -> None:
        super().__init__(
            dependencies=[Depends(management_auth)],
            former_dependencies=[Depends(DeprecatedRouteUse())],
        )
