from fastapi import Depends

from bundlemcp.api.auth import ManagementAuth
from bundlemcp.http import Controller


class ManagementController(Controller):
    """A controller every route of which requires management credentials.

    The admin-session-or-service-key check is attached once at the router, so a
    route added to a subclass cannot forget it.
    """

    def __init__(self) -> None:
        super().__init__(dependencies=[Depends(ManagementAuth())])
