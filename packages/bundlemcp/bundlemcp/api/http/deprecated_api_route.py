"""A route that answers at a renamed path's old location."""

from collections.abc import Mapping
from typing import Any, ClassVar

from fastapi.routing import APIRoute

from bundlemcp.api.http.route_deprecation import RouteDeprecation


class DeprecatedAPIRoute(APIRoute):
    """An old path kept as an alias of the route that replaced it.

    FastAPI re-creates a route from its class when a router is included under
    a prefix, so the alias's facts are class attributes of a subclass made per
    route by ``for_successor`` rather than constructor arguments.
    """

    deprecation: ClassVar[RouteDeprecation]
    former: ClassVar[str]  # the old path, relative to where the controller is mounted
    successor: ClassVar[str]  # the new path, relative to the same place

    @classmethod
    def for_successor(
        cls, deprecation: RouteDeprecation, *, former: str, successor: str
    ) -> type["DeprecatedAPIRoute"]:
        return type(
            cls.__name__,
            (cls,),
            {"deprecation": deprecation, "former": former, "successor": successor},
        )

    def successor_path(self, path: str, path_params: Mapping[str, Any]) -> str:
        """The new path a request to ``path`` should use, with its parameters filled in."""
        return self._mount_prefix(path, path_params) + self.successor.format(**path_params)

    def former_template(self, path: str, path_params: Mapping[str, Any]) -> str:
        """The old path's template as clients see it, e.g. ``/api/v1/servers/{name}``."""
        return self._mount_prefix(path, path_params) + self.former

    def _mount_prefix(self, path: str, path_params: Mapping[str, Any]) -> str:
        # Read off the request: routers included under a prefix may nest rather
        # than copy their routes, and then the route itself does not know it.
        return path.removesuffix(self.former.format(**path_params))
