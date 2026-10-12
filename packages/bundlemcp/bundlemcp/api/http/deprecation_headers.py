"""Announcing a deprecated path on every response it produces, errors included."""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bundlemcp.api.http.deprecated_api_route import DeprecatedAPIRoute


class DeprecationHeaders:
    """Adds the Deprecation, Sunset and Link headers to responses from deprecated aliases.

    A middleware rather than a route dependency, so that a response the route
    never produced itself (a 401 from authentication, a validation or service
    error) carries them too. Routing has already recorded the matched route in
    the scope by the time the response starts.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_announcing(message: Message) -> None:
            route = scope.get("route")
            if message["type"] == "http.response.start" and isinstance(route, DeprecatedAPIRoute):
                headers = MutableHeaders(scope=message)
                successor = route.successor_path(scope["path"], scope.get("path_params", {}))
                for name, value in route.deprecation.headers(successor):
                    headers.append(name, value)
            await send(message)

        await self.app(scope, receive, send_announcing)
