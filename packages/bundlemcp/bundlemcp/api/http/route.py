"""Marking a controller method as a route, to be bound when the controller is built."""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

ROUTE_ATTRIBUTE = "__bundlemcp_route__"


class RouteSpec(BaseModel):
    """What a route decorator recorded on a method: verb, path and FastAPI options."""

    model_config = ConfigDict(frozen=True)

    method: str = Field(description="HTTP verb the route answers")
    path: str = Field(description="Path relative to the controller's prefix")
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="Keyword arguments passed through to FastAPI's add_api_route",
    )


def _mark(method: str, path: str, options: dict[str, Any]) -> Callable[[Callable], Callable]:
    def decorate(handler: Callable) -> Callable:
        spec = RouteSpec(method=method, path=path, options=options)
        setattr(handler, ROUTE_ATTRIBUTE, spec)
        return handler

    return decorate


class RouteDecorators:
    """``@route.get("/{name}")`` and friends.

    Unlike ``APIRouter``'s decorators these register nothing: there is no
    router yet while the class body runs, and the method is still unbound. The
    decorator records the verb, path and options on the method; the controller
    binds every recorded method to its router when it is constructed.
    """

    def get(self, path: str, **options: Any) -> Callable[[Callable], Callable]:
        return _mark("GET", path, options)

    def post(self, path: str, **options: Any) -> Callable[[Callable], Callable]:
        return _mark("POST", path, options)

    def put(self, path: str, **options: Any) -> Callable[[Callable], Callable]:
        return _mark("PUT", path, options)

    def delete(self, path: str, **options: Any) -> Callable[[Callable], Callable]:
        return _mark("DELETE", path, options)


route = RouteDecorators()


def route_spec(handler: object) -> RouteSpec | None:
    """The route recorded on a method, or None for an ordinary method."""
    return getattr(handler, ROUTE_ATTRIBUTE, None)
