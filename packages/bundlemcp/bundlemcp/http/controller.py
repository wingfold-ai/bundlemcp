"""One HTTP surface as an object: its routes, its prefix, and the policy they share."""

from collections.abc import Sequence
from typing import ClassVar

from fastapi import APIRouter, FastAPI, params

from bundlemcp.http.route import RouteSpec, route_spec


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
            self.router.add_api_route(
                spec.path, getattr(self, name), methods=[spec.method], **options
            )

    @classmethod
    def _routes(cls) -> list[tuple[str, RouteSpec]]:
        """Every decorated method of the class, in the order the decorators ran."""
        found = [
            (name, spec)
            for name in dir(cls)
            if not name.startswith("_") and (spec := route_spec(getattr(cls, name))) is not None
        ]
        return sorted(found, key=lambda item: item[1].order)

    def mount(self, app: FastAPI, *, prefix: str = "") -> None:
        app.include_router(self.router, prefix=prefix)
