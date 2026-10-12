"""One HTTP surface as an object: its routes, its prefix, and the policy they share."""

from collections.abc import Sequence
from typing import ClassVar

from fastapi import APIRouter, FastAPI, params

from bundlemcp.api.http.deprecated_api_route import DeprecatedAPIRoute
from bundlemcp.api.http.route import RouteSpec, route_spec
from bundlemcp.api.http.route_deprecation import RouteDeprecation


class Controller:
    """A group of related routes declared as decorated methods of one class.

    A subclass names its ``prefix`` and ``tags`` and marks handler methods with
    ``@route.get`` and friends. Constructing the controller binds every marked
    method, bound to the instance, onto its router in the order they were
    written. Anything every route of the surface needs (authentication, a
    common dependency) is declared once through ``dependencies`` instead of
    repeated per route.

    A renamed surface keeps answering at its old paths for a deprecation
    window: ``former_prefix`` moves every route at once, a route's own
    ``former_path`` moves just that one. Each old path is bound to the same
    handler as an alias left out of the OpenAPI document, with
    ``former_dependencies`` added to it.
    """

    prefix: ClassVar[str] = ""
    tags: ClassVar[Sequence[str]] = ()
    include_in_schema: ClassVar[bool] = True
    former_prefix: ClassVar[str | None] = None
    deprecation: ClassVar[RouteDeprecation | None] = None

    def __init__(
        self,
        *,
        dependencies: Sequence[params.Depends] = (),
        former_dependencies: Sequence[params.Depends] = (),
    ) -> None:
        self.router = APIRouter(
            prefix=self.prefix, tags=list(self.tags), dependencies=list(dependencies)
        )
        self.former_router = APIRouter(dependencies=list(dependencies))
        for name, spec in self._routes():
            handler = getattr(self, name)
            options = {"include_in_schema": self.include_in_schema, **spec.options}
            self.router.add_api_route(spec.path, handler, methods=[spec.method], **options)
            for former in self._former_paths(spec):
                self._bind_former(former, spec, handler, options, former_dependencies)

    def _former_paths(self, spec: RouteSpec) -> list[str]:
        paths = []
        if self.former_prefix is not None:
            paths.append(self.former_prefix + spec.path)
        if spec.former_path is not None:
            paths.append(self.prefix + spec.former_path)
        return paths

    def _bind_former(
        self,
        former: str,
        spec: RouteSpec,
        handler: object,
        options: dict,
        former_dependencies: Sequence[params.Depends],
    ) -> None:
        if self.deprecation is None:
            raise TypeError(f"{type(self).__name__} keeps former paths but names no deprecation")
        route_class = DeprecatedAPIRoute.for_successor(
            self.deprecation, former=former, successor=self.prefix + spec.path
        )
        self.former_router.add_api_route(
            former,
            handler,
            methods=[spec.method],
            **{
                **options,
                "include_in_schema": False,
                "dependencies": [*options.get("dependencies", ()), *former_dependencies],
            },
            route_class_override=route_class,
        )

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
        if self.former_router.routes:
            app.include_router(self.former_router, prefix=prefix)
