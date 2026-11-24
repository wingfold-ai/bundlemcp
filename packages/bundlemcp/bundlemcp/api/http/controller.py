"""One HTTP surface as an object: its routes, its prefix, and the policy they share."""

from collections.abc import Sequence
from typing import ClassVar

from fastapi import APIRouter, FastAPI, params

from bundlemcp.api.http.route import RouteSpec, route_spec

# The OpenAPI extension naming the access a route needs (a key scope, or "full").
ACCESS_EXTENSION = "x-bundlemcp-access"


class Controller:
    """A group of related routes declared as decorated methods of one class.

    A subclass names its ``prefix`` and ``tags`` and marks handler methods with
    ``@route.get`` and friends. Constructing the controller binds every marked
    method, bound to the instance, onto its router in the order they were
    written. Anything every route of the surface needs (authentication, a
    common dependency) is declared once through ``dependencies`` instead of
    repeated per route.
    """

    prefix: ClassVar[str] = ""
    tags: ClassVar[Sequence[str]] = ()
    include_in_schema: ClassVar[bool] = True

    def __init__(self, *, dependencies: Sequence[params.Depends] = ()) -> None:
        self.router = APIRouter(
            prefix=self.prefix, tags=list(self.tags), dependencies=list(dependencies)
        )
        for name, spec in self._routes():
            options = {"include_in_schema": self.include_in_schema, **spec.options}
            extra = list(options.pop("dependencies", ())) + self._route_dependencies(name, spec)
            if spec.access is not None:
                # published so the OpenAPI document and the route audit can see it
                options["openapi_extra"] = {
                    **options.get("openapi_extra", {}),
                    ACCESS_EXTENSION: str(spec.access),
                }
            self.router.add_api_route(
                spec.path,
                getattr(self, name),
                methods=[spec.method],
                dependencies=extra,
                **options,
            )

    def _route_dependencies(self, name: str, spec: RouteSpec) -> list[params.Depends]:
        """Dependencies one route adds to the router's own; none by default."""
        return []

    @classmethod
    def _routes(cls) -> list[tuple[str, RouteSpec]]:
        """Every decorated method of the class, in the order it was written.

        Base classes contribute first, then each subclass in turn, so an
        overriding method keeps its route's position. A subclass that overrides
        a routed method without decorating it again would silently drop the
        route, so that is refused here rather than discovered at request time.
        """
        found: dict[str, RouteSpec] = {}
        for klass in reversed(cls.__mro__):
            for name, attribute in vars(klass).items():
                if name.startswith("_"):
                    continue
                spec = route_spec(attribute)
                if spec is not None:
                    found[name] = spec
                elif name in found:
                    raise TypeError(
                        f"{klass.__name__}.{name} overrides a route without @route; "
                        "decorate it again or rename it"
                    )
        return list(found.items())

    def mount(self, app: FastAPI, *, prefix: str = "") -> None:
        app.include_router(self.router, prefix=prefix)
