"""Token introspection (RFC 7662), for resource servers that hold a service key."""

from typing import Annotated

from fastapi import Depends, Form

from bundlemcp.api.http.controller import Controller
from bundlemcp.api.http.route import route
from bundlemcp.api.oauth.introspection_auth import IntrospectionAuth
from bundlemcp.api.oauth.providers import IntrospectionServiceProvider
from bundlemcp.application.schemas import IntrospectionResponse


class IntrospectionController(Controller):
    """Every route here requires a service-kind API key."""

    prefix = "/oauth"
    tags = ("oauth",)
    include_in_schema = False

    def __init__(self) -> None:
        super().__init__(dependencies=[Depends(IntrospectionAuth())])

    @route.post("/introspect", response_model_exclude_none=True)
    async def introspect(
        self, service: IntrospectionServiceProvider, token: Annotated[str, Form()]
    ) -> IntrospectionResponse:
        """Reports whether the token is good, its subject and its endpoint audience."""
        return await service.introspect(token)
